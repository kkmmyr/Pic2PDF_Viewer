"""Qwen3-Reranker MLX を隔離 lexical 候補へ適用して評価する。

MLX を含む repo 外 venv で実行する。入力は ``eval_novel_search.py`` の結果
JSON と read-only SQLite で、本番 DB / LanceDB / API 設定は変更しない。結果には
本文を保存せず、ページ参照、順位、score、token 数、latency だけを記録する。

使用例::

    /path/to/pic2pdf-mlx/.venv/bin/python \
      backend/scripts/eval_novel_reranker_mlx.py \
      --sqlite /tmp/search-eval/novel.db \
      --fixture backend/scripts/fixtures/novel_search_eval_v1.json \
      --retrieval-result /tmp/search-eval/lexical-result.json \
      --snapshot-label 2026-08-22_020001 \
      --output /tmp/search-eval/reranker-result.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import statistics
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__:
    from scripts.novel_eval_metrics import metrics_for_ranking as _ranking_metrics
    from scripts.novel_eval_runtime import process_max_rss_bytes as _max_rss_bytes
else:
    from novel_eval_metrics import metrics_for_ranking as _ranking_metrics
    from novel_eval_runtime import process_max_rss_bytes as _max_rss_bytes

SCHEMA_VERSION = 1
MODEL_ID = "mlx-community/Qwen3-Reranker-0.6B-4bit"
MODEL_REVISION = "5f324548f1d20c2b5a450f126fc6ef2fb1126524"
DEFAULT_MODEL = Path("/Users/medaro/.local/share/pic2pdf-mlx/models/qwen3-reranker-0.6b-4bit")
DEFAULT_FIXTURE = Path(__file__).with_name("fixtures") / "novel_search_eval_v1.json"
DEFAULT_INSTRUCTION = "Given a web search query, retrieve relevant passages that answer the query"
PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements "
    "based on the Query and the Instruct provided. Note that the answer can "
    'only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
)
SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
EXPECTED_MODEL_FILES = {
    "model.safetensors": "1d212560a5b1c36186787fdae19f11f20fecfc29bef91522e12a8e0d118f4545",
    "tokenizer.json": "be75606093db2094d7cd20f3c2f385c212750648bd6ea4fb2bf507a6a4c55506",
    "tokenizer_config.json": "1689852cc9c45010de040c8302a8acdc0d2c4c6c740dd7e9dd0a8c704e16eada",
    "config.json": "09adff58b65e9305009c9caa4923b3365b18dd2f84135b44168aaf869278bea4",
    "model.safetensors.index.json": "90d82744cdb6b7d093f0b812fc21a49b6ffa9d0084a45428f0cfd01eb4adbe12",
    "generation_config.json": "81051cd3f6e77013827148d0b8a6ead93f8ac390d5ab805f849199f0af6a08db",
    "chat_template.jinja": "6f682162495ec5b39fd9005c01b6aa2a74669379fe967039f1e2cbbe8752369d",
}


@dataclass(frozen=True, order=True)
class PageKey:
    book_name: str
    page_no: int


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    query: str
    relevant: dict[PageKey, int]


@dataclass(frozen=True)
class Candidate:
    key: PageKey
    source_rank: int


@dataclass(frozen=True)
class Score:
    logit_difference: float
    probability: float
    input_tokens: int
    latency_ms: float


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil((percentile / 100.0) * len(ordered)))
    return ordered[rank - 1]


def _mean(values: Sequence[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def verify_model(path: Path) -> dict[str, Any]:
    if not path.is_dir():
        raise FileNotFoundError(f"reranker model directory not found: {path}")
    python_files = sorted(item.name for item in path.glob("*.py"))
    if python_files:
        raise RuntimeError(f"checkpoint contains executable Python files: {python_files}")
    hashes: dict[str, str] = {}
    for name, expected in EXPECTED_MODEL_FILES.items():
        file_path = path / name
        if not file_path.is_file():
            raise FileNotFoundError(f"required model file is missing: {file_path}")
        actual = _sha256_file(file_path)
        if actual != expected:
            raise RuntimeError(f"model file SHA-256 mismatch: {name}: {actual}")
        hashes[name] = actual
    config = json.loads((path / "config.json").read_text(encoding="utf-8"))
    if config.get("model_type") != "qwen3" or config.get("architectures") != ["Qwen3ForCausalLM"]:
        raise RuntimeError("unexpected reranker model architecture")
    if config.get("quantization") != {"group_size": 64, "bits": 4, "mode": "affine"}:
        raise RuntimeError("unexpected reranker quantization config")
    return {
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "path_name": path.name,
        "files": hashes,
        "model_type": config["model_type"],
        "architecture": config["architectures"][0],
        "quantization": config["quantization"],
        "trust_remote_code": False,
    }


def load_cases(path: Path) -> dict[str, EvalCase]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported fixture")
    raw_cases = value.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("fixture cases are missing")
    cases: dict[str, EvalCase] = {}
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise ValueError("fixture case is not an object")
        case_id = raw.get("id")
        query = raw.get("query")
        relevant_rows = raw.get("relevant")
        if not isinstance(case_id, str) or not case_id or case_id in cases:
            raise ValueError(f"invalid or duplicate case id: {case_id!r}")
        if not isinstance(query, str) or not query:
            raise ValueError(f"case {case_id}: query is missing")
        if not isinstance(relevant_rows, list) or not relevant_rows:
            raise ValueError(f"case {case_id}: relevant pages are missing")
        relevant: dict[PageKey, int] = {}
        for row in relevant_rows:
            if not isinstance(row, dict):
                raise ValueError(f"case {case_id}: relevant page is not an object")
            key = PageKey(book_name=str(row["book_name"]), page_no=int(row["page_no"]))
            grade = int(row["grade"])
            if key in relevant or grade < 1 or grade > 3:
                raise ValueError(f"case {case_id}: invalid relevant page {key}")
            relevant[key] = grade
        cases[case_id] = EvalCase(case_id=case_id, query=query, relevant=relevant)
    return cases


def load_candidates(
    path: Path,
    *,
    expected_fixture_sha256: str,
    method: str,
    limit: int,
) -> tuple[dict[str, list[Candidate]], dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported retrieval result")
    fixture = value.get("fixture")
    if not isinstance(fixture, dict) or fixture.get("sha256") != expected_fixture_sha256:
        raise RuntimeError("retrieval result fixture SHA-256 does not match")
    methods = value.get("methods")
    if not isinstance(methods, dict) or method not in methods:
        raise ValueError(f"candidate method is missing: {method}")
    method_result = methods[method]
    if not isinstance(method_result, dict) or not isinstance(method_result.get("cases"), list):
        raise ValueError(f"candidate method result is malformed: {method}")

    candidates: dict[str, list[Candidate]] = {}
    for case in method_result["cases"]:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str):
            raise ValueError("candidate case is malformed")
        ranking = case.get("ranking")
        if not isinstance(ranking, list):
            raise ValueError(f"candidate ranking is missing: {case.get('id')}")
        rows: list[Candidate] = []
        seen: set[PageKey] = set()
        for row in ranking[:limit]:
            if not isinstance(row, dict):
                raise ValueError("candidate row is malformed")
            key = PageKey(book_name=str(row["book_name"]), page_no=int(row["page_no"]))
            if key in seen:
                raise ValueError(f"duplicate candidate page: {key}")
            seen.add(key)
            rows.append(Candidate(key=key, source_rank=int(row["rank"])))
        candidates[case["id"]] = rows
    return candidates, method_result


def open_sqlite_read_only(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"SQLite DB not found: {path}")
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def load_candidate_texts(
    conn: sqlite3.Connection,
    candidates: dict[str, list[Candidate]],
) -> dict[PageKey, str]:
    keys = {candidate.key for rows in candidates.values() for candidate in rows}
    result: dict[PageKey, str] = {}
    for key in sorted(keys):
        row = conn.execute(
            """
            SELECT COALESCE(p.full_text, '')
            FROM pages p
            JOIN books b ON b.id = p.book_id
            WHERE b.name = ? AND p.page_no = ? AND p.index_eligible = 1
            """,
            (key.book_name, key.page_no),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"candidate page not found in isolated SQLite: {key}")
        result[key] = str(row[0])
    return result


def build_pair_token_ids(
    tokenizer: Any,
    *,
    prefix_tokens: Sequence[int],
    suffix_tokens: Sequence[int],
    instruction: str,
    query: str,
    document: str,
    max_length: int,
) -> list[int]:
    available = max_length - len(prefix_tokens) - len(suffix_tokens)
    if available < 1:
        raise ValueError("max_length is too small for reranker prefix and suffix")
    content = f"<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {document}"
    content_tokens = tokenizer.encode(content, add_special_tokens=False)[:available]
    return [*prefix_tokens, *content_tokens, *suffix_tokens]


class Qwen3Reranker:
    def __init__(self, model_path: Path, *, instruction: str, max_length: int) -> None:
        import mlx.core as mx
        from mlx_lm import load

        self._mx = mx
        started = time.perf_counter()
        self._model, tokenizer = load(str(model_path))
        mx.eval(self._model.parameters())
        self.load_seconds = time.perf_counter() - started
        self._tokenizer = getattr(tokenizer, "_tokenizer", tokenizer)
        self._prefix_tokens = self._tokenizer.encode(PREFIX, add_special_tokens=False)
        self._suffix_tokens = self._tokenizer.encode(SUFFIX, add_special_tokens=False)
        self._yes_id = self._tokenizer.convert_tokens_to_ids("yes")
        self._no_id = self._tokenizer.convert_tokens_to_ids("no")
        if not isinstance(self._yes_id, int) or not isinstance(self._no_id, int) or self._yes_id == self._no_id:
            raise RuntimeError("reranker yes/no token IDs are invalid")
        self.instruction = instruction
        self.max_length = max_length

    def score(self, query: str, document: str) -> Score:
        ids = build_pair_token_ids(
            self._tokenizer,
            prefix_tokens=self._prefix_tokens,
            suffix_tokens=self._suffix_tokens,
            instruction=self.instruction,
            query=query,
            document=document,
            max_length=self.max_length,
        )
        started = time.perf_counter()
        logits = self._model(self._mx.array([ids]))[0, -1, :]
        pair = self._mx.stack([logits[self._no_id], logits[self._yes_id]])
        log_probability = pair - self._mx.logsumexp(pair)
        probability = self._mx.exp(log_probability[1])
        difference = pair[1] - pair[0]
        self._mx.eval(probability, difference)
        latency_ms = (time.perf_counter() - started) * 1000.0
        return Score(
            logit_difference=float(difference),
            probability=float(probability),
            input_tokens=len(ids),
            latency_ms=latency_ms,
        )

    def warmup(self) -> Score:
        return self.score("日本の首都", "日本の首都は東京である。")

    def memory(self) -> dict[str, int | None]:
        active = getattr(self._mx, "get_active_memory", None)
        peak = getattr(self._mx, "get_peak_memory", None)
        return {
            "mlx_active_bytes": int(active()) if callable(active) else None,
            "mlx_peak_bytes": int(peak()) if callable(peak) else None,
            "process_max_rss_bytes": _max_rss_bytes(),
        }


def metrics_for_ranking(ranking: Sequence[PageKey], relevant: dict[PageKey, int]) -> dict[str, float]:
    return _ranking_metrics(ranking, relevant)


def _aggregate(case_results: Sequence[dict[str, Any]], latencies: Sequence[float]) -> dict[str, Any]:
    metrics = ("recall_at_5", "recall_at_10", "recall_at_30", "mrr_at_10", "ndcg_at_10")
    result = {name: _mean([float(case["metrics"][name]) for case in case_results]) for name in metrics}
    result.update(
        {
            "case_count": len(case_results),
            "latency_ms_p50_per_pair": _percentile(latencies, 50),
            "latency_ms_p95_per_pair": _percentile(latencies, 95),
            "latency_ms_mean_per_pair": _mean(latencies),
        }
    )
    return result


def _relative_change(new: float, old: float) -> float | None:
    return new / old - 1.0 if old else None


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", required=True, type=Path)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--retrieval-result", required=True, type=Path)
    parser.add_argument("--candidate-method", default="lance_icu_ngram_rrf")
    parser.add_argument("--candidate-limit", type=int, default=30)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--instruction", default=DEFAULT_INSTRUCTION)
    parser.add_argument("--max-length", type=int, default=8192)
    parser.add_argument("--snapshot-label", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.candidate_limit < 10 or args.candidate_limit > 100:
        raise ValueError("--candidate-limit must be between 10 and 100")
    if args.max_length < 512 or args.max_length > 32768:
        raise ValueError("--max-length must be between 512 and 32768")

    started_at = datetime.now(UTC)
    model_manifest = verify_model(args.model)
    fixture_sha256 = _sha256_file(args.fixture)
    cases = load_cases(args.fixture)
    candidates, source_method = load_candidates(
        args.retrieval_result,
        expected_fixture_sha256=fixture_sha256,
        method=args.candidate_method,
        limit=args.candidate_limit,
    )
    if set(candidates) != set(cases):
        raise RuntimeError("fixture cases and retrieval result cases differ")

    sqlite_hash_before = _sha256_file(args.sqlite)
    conn = open_sqlite_read_only(args.sqlite)
    try:
        if str(conn.execute("PRAGMA integrity_check").fetchone()[0]) != "ok":
            raise RuntimeError("SQLite integrity_check failed")
        texts = load_candidate_texts(conn, candidates)
    finally:
        conn.close()

    scorer = Qwen3Reranker(args.model, instruction=args.instruction, max_length=args.max_length)
    warmup = scorer.warmup()
    case_results: list[dict[str, Any]] = []
    all_latencies: list[float] = []
    all_tokens: list[int] = []
    total_pairs = sum(len(rows) for rows in candidates.values())
    done_pairs = 0
    scoring_started = time.perf_counter()

    for case_id, case in cases.items():
        scored: list[tuple[Candidate, Score]] = []
        for candidate in candidates[case_id]:
            score = scorer.score(case.query, texts[candidate.key])
            scored.append((candidate, score))
            all_latencies.append(score.latency_ms)
            all_tokens.append(score.input_tokens)
            done_pairs += 1
            if done_pairs % 25 == 0 or done_pairs == total_pairs:
                print(
                    json.dumps(
                        {
                            "event": "progress",
                            "pairs": done_pairs,
                            "total_pairs": total_pairs,
                            "case": case_id,
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
        scored.sort(key=lambda item: (-item[1].logit_difference, item[0].source_rank, item[0].key))
        ranking = [candidate.key for candidate, _ in scored]
        case_results.append(
            {
                "id": case_id,
                "query": case.query,
                "candidate_count": len(scored),
                "metrics": metrics_for_ranking(ranking, case.relevant),
                "ranking": [
                    {
                        "rank": rank,
                        "book_name": candidate.key.book_name,
                        "page_no": candidate.key.page_no,
                        "source_rank": candidate.source_rank,
                        "logit_difference": score.logit_difference,
                        "probability": score.probability,
                        "input_tokens": score.input_tokens,
                        "latency_ms": score.latency_ms,
                        "relevance_grade": case.relevant.get(candidate.key, 0),
                    }
                    for rank, (candidate, score) in enumerate(scored, start=1)
                ],
            }
        )

    scoring_seconds = time.perf_counter() - scoring_started
    reranked_aggregate = _aggregate(case_results, all_latencies)
    source_aggregate = source_method["aggregate"]
    regressions = [
        case["id"]
        for case in case_results
        if float(case["metrics"]["recall_at_10"])
        < float(next(row for row in source_method["cases"] if row["id"] == case["id"])["metrics"]["recall_at_10"])
    ]
    memory = scorer.memory()
    peak_bytes = max(
        int(memory["mlx_peak_bytes"] or 0),
        int(memory["process_max_rss_bytes"] or 0),
    )
    mrr_relative = _relative_change(float(reranked_aggregate["mrr_at_10"]), float(source_aggregate["mrr_at_10"]))
    ndcg_relative = _relative_change(
        float(reranked_aggregate["ndcg_at_10"]),
        float(source_aggregate["ndcg_at_10"]),
    )
    gate = {
        "candidate_recall_at_30_unchanged": math.isclose(
            float(reranked_aggregate["recall_at_30"]),
            float(source_aggregate["recall_at_30"]),
        ),
        "recall_at_10_regressions": regressions,
        "mrr_at_10_relative_change": mrr_relative,
        "ndcg_at_10_relative_change": ndcg_relative,
        "quality_improves_by_5_percent": bool(
            (mrr_relative is not None and mrr_relative >= 0.05) or (ndcg_relative is not None and ndcg_relative >= 0.05)
        ),
        "pair_latency_p95_under_2_seconds": float(reranked_aggregate["latency_ms_p95_per_pair"]) <= 2000.0,
        "peak_memory_under_4_gib": peak_bytes <= 4 * 1024**3,
    }
    gate["pass"] = bool(
        gate["candidate_recall_at_30_unchanged"]
        and not regressions
        and gate["quality_improves_by_5_percent"]
        and gate["pair_latency_p95_under_2_seconds"]
        and gate["peak_memory_under_4_gib"]
    )

    sqlite_hash_after = _sha256_file(args.sqlite)
    if sqlite_hash_after != sqlite_hash_before:
        raise RuntimeError("isolated SQLite changed during reranker evaluation")
    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "started_at": started_at.isoformat(),
        "snapshot_label": args.snapshot_label,
        "fixture": {
            "file_name": args.fixture.name,
            "sha256": fixture_sha256,
            "case_count": len(cases),
        },
        "source": {
            "retrieval_result_file": args.retrieval_result.name,
            "retrieval_result_sha256": _sha256_file(args.retrieval_result),
            "candidate_method": args.candidate_method,
            "candidate_limit": args.candidate_limit,
            "aggregate": source_aggregate,
        },
        "model": {
            **model_manifest,
            "instruction": args.instruction,
            "max_length": args.max_length,
            "scoring": "softmax([logit(no), logit(yes)])[yes] and yes-minus-no ordering",
            "load_seconds": scorer.load_seconds,
            "warmup": {
                "input_tokens": warmup.input_tokens,
                "latency_ms": warmup.latency_ms,
            },
        },
        "runtime": {
            "python": sys.version,
            "total_pairs": total_pairs,
            "scoring_seconds": scoring_seconds,
            "input_tokens_min": min(all_tokens),
            "input_tokens_max": max(all_tokens),
            "input_tokens_mean": _mean(all_tokens),
            "memory": memory,
        },
        "reranked": {
            "aggregate": reranked_aggregate,
            "cases": case_results,
        },
        "comparison": gate,
        "safety": {
            "sqlite_sha256_before": sqlite_hash_before,
            "sqlite_sha256_after": sqlite_hash_after,
            "source_text_in_result": False,
            "production_paths_modified": False,
        },
    }
    _write_json(args.output, result)
    print(
        json.dumps(
            {
                "event": "complete",
                "output": str(args.output),
                "source_aggregate": source_aggregate,
                "reranked_aggregate": reranked_aggregate,
                "comparison": gate,
                "runtime": result["runtime"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
