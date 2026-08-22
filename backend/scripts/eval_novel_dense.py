"""隔離生成した embedding を LanceDB exact search で比較評価する。

``export_novel_embeddings_mlx.py`` の NPZ と manifest を検証し、モデルごとに
別の LanceDB table を新規作成する。検索品質の比較では ANN 近似誤差を混ぜないため
ベクトル index を作らず exact cosine search を使う。lexical 結果が指定された場合は
固定済み LanceDB ICU 順位との RRF も同時に評価する。本文・snippet・embedding は
結果 JSON に保存しない。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import statistics
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import lancedb
import numpy as np
import pyarrow as pa

SCHEMA_VERSION = 1
DEFAULT_FIXTURE = Path(__file__).with_name("fixtures") / "novel_search_eval_v1.json"


@dataclass(frozen=True, order=True)
class PageKey:
    book_name: str
    page_no: int


@dataclass(frozen=True)
class SearchHit:
    key: PageKey
    score: float


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    query: str
    scope_book: str | None
    relevant: dict[PageKey, int]
    source: str


SearchFn = Callable[[EvalCase, int], list[SearchHit]]


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


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_fixture(path: Path) -> tuple[dict[str, Any], list[EvalCase]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported fixture")
    raw_cases = value.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("fixture cases are missing")
    cases: list[EvalCase] = []
    seen_ids: set[str] = set()
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise ValueError("fixture case is not an object")
        case_id = raw.get("id")
        query = raw.get("query")
        scope = raw.get("scope", {"type": "all"})
        relevant_rows = raw.get("relevant")
        if not isinstance(case_id, str) or not case_id or case_id in seen_ids:
            raise ValueError(f"invalid or duplicate case id: {case_id!r}")
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"case {case_id}: query is missing")
        if not isinstance(scope, dict) or scope.get("type") not in {"all", "book"}:
            raise ValueError(f"case {case_id}: unsupported scope")
        scope_book = scope.get("book_name") if scope.get("type") == "book" else None
        if scope_book is not None and not isinstance(scope_book, str):
            raise ValueError(f"case {case_id}: book scope is invalid")
        if not isinstance(relevant_rows, list) or not relevant_rows:
            raise ValueError(f"case {case_id}: relevant pages are missing")
        relevant: dict[PageKey, int] = {}
        for row in relevant_rows:
            if not isinstance(row, dict):
                raise ValueError(f"case {case_id}: relevant page is invalid")
            key = PageKey(book_name=str(row["book_name"]), page_no=int(row["page_no"]))
            grade = int(row["grade"])
            if key in relevant or grade < 1 or grade > 3:
                raise ValueError(f"case {case_id}: invalid relevant page {key}")
            relevant[key] = grade
        seen_ids.add(case_id)
        cases.append(
            EvalCase(
                case_id=case_id,
                query=query,
                scope_book=scope_book,
                relevant=relevant,
                source=str(raw.get("source", "")),
            )
        )
    return value, cases


def open_sqlite_read_only(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"SQLite DB not found: {path}")
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro&immutable=1", uri=True)


def _validate_manifest(
    path: Path,
    *,
    artifact: Path,
    fixture_sha256: str,
    sqlite_sha256: str,
) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported embedding manifest")
    if value.get("fixture", {}).get("sha256") != fixture_sha256:
        raise RuntimeError("embedding manifest fixture SHA-256 does not match")
    if value.get("corpus", {}).get("sqlite_sha256") != sqlite_sha256:
        raise RuntimeError("embedding manifest SQLite SHA-256 does not match")
    artifact_info = value.get("artifact")
    if not isinstance(artifact_info, dict):
        raise ValueError("embedding manifest artifact section is missing")
    if artifact_info.get("sha256") != _sha256_file(artifact):
        raise RuntimeError("embedding artifact SHA-256 does not match manifest")
    if artifact_info.get("contains_source_text") is not False:
        raise RuntimeError("embedding artifact source-text contract is missing")
    return value


def _load_artifact(
    path: Path,
    *,
    expected_query_ids: Sequence[str],
) -> dict[str, Any]:
    with np.load(path, allow_pickle=False) as data:
        required = {
            "schema_version",
            "chunk_ids",
            "book_names",
            "page_nos",
            "chunk_indices",
            "document_vectors",
            "query_ids",
            "query_vectors",
        }
        if set(data.files) != required:
            raise ValueError(f"unexpected embedding artifact arrays: {data.files}")
        if data["schema_version"].tolist() != [SCHEMA_VERSION]:
            raise ValueError("unsupported embedding artifact schema")
        result = {name: np.array(data[name], copy=True) for name in required if name != "schema_version"}

    count = len(result["chunk_ids"])
    aligned = (
        len(result["book_names"]),
        len(result["page_nos"]),
        len(result["chunk_indices"]),
        len(result["document_vectors"]),
    )
    if any(length != count for length in aligned) or count == 0:
        raise ValueError("embedding artifact document arrays are not aligned")
    if len(set(int(value) for value in result["chunk_ids"])) != count:
        raise ValueError("embedding artifact contains duplicate chunk IDs")
    query_ids = [str(value) for value in result["query_ids"]]
    if query_ids != list(expected_query_ids):
        raise RuntimeError("embedding artifact query order differs from fixture")
    document_vectors = result["document_vectors"]
    query_vectors = result["query_vectors"]
    if document_vectors.ndim != 2 or query_vectors.ndim != 2:
        raise ValueError("embedding vectors must be two-dimensional")
    if document_vectors.shape[1] != query_vectors.shape[1]:
        raise ValueError("document and query dimensions differ")
    if document_vectors.dtype != np.float32 or query_vectors.dtype != np.float32:
        raise ValueError("embedding vectors must be float32")
    if not np.isfinite(document_vectors).all() or not np.isfinite(query_vectors).all():
        raise ValueError("embedding artifact contains non-finite values")
    return result


def _build_lance_table(artifact: dict[str, Any], destination: Path) -> tuple[Any, dict[str, Any]]:
    if destination.exists():
        raise FileExistsError(f"comparison index already exists: {destination}")
    destination.mkdir(parents=True)
    vectors = artifact["document_vectors"]
    dimension = int(vectors.shape[1])
    flattened = pa.array(vectors.reshape(-1), type=pa.float32())
    vector_array = pa.FixedSizeListArray.from_arrays(flattened, dimension)
    arrow = pa.table(
        {
            "chunk_id": pa.array(artifact["chunk_ids"], type=pa.int64()),
            "book_name": pa.array(artifact["book_names"].tolist(), type=pa.string()),
            "page_no": pa.array(artifact["page_nos"], type=pa.int32()),
            "chunk_idx": pa.array(artifact["chunk_indices"], type=pa.int32()),
            "embedding": vector_array,
        }
    )
    started = time.perf_counter()
    database = lancedb.connect(destination)
    table = database.create_table("chunks", data=arrow)
    build_seconds = time.perf_counter() - started
    counts = Counter(
        (str(book), int(page)) for book, page in zip(artifact["book_names"], artifact["page_nos"], strict=True)
    )
    info = {
        "storage": "LanceDB",
        "search_mode": "exact cosine; no ANN index",
        "build_seconds": build_seconds,
        "directory_size_bytes": sum(item.stat().st_size for item in destination.rglob("*") if item.is_file()),
        "indexed_chunks": int(table.count_rows()),
        "indexed_pages": len(counts),
        "max_chunks_per_page": max(counts.values()),
        "dimension": dimension,
        "table_name": "chunks",
        "vector_column": "embedding",
        "vector_indices": table.list_indices(),
    }
    return table, info


def _lance_filter(book_name: str) -> str:
    escaped = book_name.replace("'", "''")
    return f"book_name = '{escaped}'"


def _dense_search(
    table: Any,
    query_vector: np.ndarray,
    case: EvalCase,
    *,
    limit: int,
    max_chunks_per_page: int,
) -> list[SearchHit]:
    fetch_limit = limit * max_chunks_per_page
    builder = (
        table.search(query_vector, vector_column_name="embedding")
        .distance_type("cosine")
        .limit(fetch_limit)
        .select(["book_name", "page_no", "_distance"])
    )
    if case.scope_book is not None:
        builder = builder.where(_lance_filter(case.scope_book), prefilter=True)
    rows = builder.to_list()
    hits: list[SearchHit] = []
    seen: set[PageKey] = set()
    for row in rows:
        key = PageKey(book_name=str(row["book_name"]), page_no=int(row["page_no"]))
        if key in seen:
            continue
        seen.add(key)
        hits.append(SearchHit(key=key, score=-float(row["_distance"])))
        if len(hits) == limit:
            break
    return hits


def _load_lexical_rankings(
    path: Path,
    *,
    method: str,
    fixture_sha256: str,
) -> tuple[dict[str, list[SearchHit]], dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported lexical result")
    if value.get("fixture", {}).get("sha256") != fixture_sha256:
        raise RuntimeError("lexical result fixture SHA-256 does not match")
    method_result = value.get("methods", {}).get(method)
    if not isinstance(method_result, dict) or not isinstance(method_result.get("cases"), list):
        raise ValueError(f"lexical result method is missing: {method}")
    rankings: dict[str, list[SearchHit]] = {}
    for case in method_result["cases"]:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str):
            raise ValueError("lexical result case is malformed")
        rankings[case["id"]] = [
            SearchHit(
                key=PageKey(book_name=str(row["book_name"]), page_no=int(row["page_no"])),
                score=float(row["score"]),
            )
            for row in case.get("ranking", [])
        ]
    return rankings, method_result


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[SearchHit]],
    *,
    limit: int,
    k_rrf: int = 60,
) -> list[SearchHit]:
    scores: dict[PageKey, float] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            scores[hit.key] = scores.get(hit.key, 0.0) + 1.0 / (k_rrf + rank)
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [SearchHit(key=key, score=score) for key, score in ordered[:limit]]


def metrics_for_ranking(hits: Sequence[SearchHit], relevant: dict[PageKey, int]) -> dict[str, float]:
    ranked_keys = [hit.key for hit in hits]
    relevant_keys = set(relevant)

    def recall_at(k: int) -> float:
        return len(relevant_keys & set(ranked_keys[:k])) / len(relevant_keys)

    reciprocal_rank = 0.0
    for rank, key in enumerate(ranked_keys[:10], start=1):
        if key in relevant_keys:
            reciprocal_rank = 1.0 / rank
            break
    dcg = sum(
        ((2 ** relevant.get(key, 0)) - 1) / math.log2(rank + 1)
        for rank, key in enumerate(ranked_keys[:10], start=1)
        if key in relevant
    )
    ideal_grades = sorted(relevant.values(), reverse=True)[:10]
    ideal_dcg = sum(((2**grade) - 1) / math.log2(rank + 1) for rank, grade in enumerate(ideal_grades, start=1))
    return {
        "recall_at_5": recall_at(5),
        "recall_at_10": recall_at(10),
        "recall_at_30": recall_at(30),
        "mrr_at_10": reciprocal_rank,
        "ndcg_at_10": dcg / ideal_dcg if ideal_dcg else 0.0,
    }


def evaluate_method(
    name: str,
    cases: Sequence[EvalCase],
    search: SearchFn,
    *,
    limit: int,
    warmup_runs: int,
    measured_runs: int,
    build_info: dict[str, Any],
) -> dict[str, Any]:
    case_results: list[dict[str, Any]] = []
    all_latencies: list[float] = []
    metric_names = (
        "recall_at_5",
        "recall_at_10",
        "recall_at_30",
        "mrr_at_10",
        "ndcg_at_10",
    )
    for case in cases:
        for _ in range(warmup_runs):
            search(case, limit)
        rankings: list[list[SearchHit]] = []
        latencies: list[float] = []
        for _ in range(measured_runs):
            started = time.perf_counter()
            ranking = search(case, limit)
            latencies.append((time.perf_counter() - started) * 1000.0)
            rankings.append(ranking)
        all_latencies.extend(latencies)
        first = rankings[0]
        first_keys = [hit.key for hit in first]
        deterministic = all([hit.key for hit in ranking] == first_keys for ranking in rankings[1:])
        case_results.append(
            {
                "id": case.case_id,
                "query": case.query,
                "scope": (
                    {"type": "book", "book_name": case.scope_book} if case.scope_book is not None else {"type": "all"}
                ),
                "source": case.source,
                "hit_count": len(first),
                "metrics": metrics_for_ranking(first, case.relevant),
                "ranking": [
                    {
                        "rank": rank,
                        "book_name": hit.key.book_name,
                        "page_no": hit.key.page_no,
                        "score": hit.score,
                        "relevance_grade": case.relevant.get(hit.key, 0),
                    }
                    for rank, hit in enumerate(first, start=1)
                ],
                "latency_ms": {
                    "runs": latencies,
                    "mean": _mean(latencies),
                    "p50": _percentile(latencies, 50),
                    "p95": _percentile(latencies, 95),
                },
                "deterministic": deterministic,
            }
        )
    aggregate = {metric: _mean([float(case["metrics"][metric]) for case in case_results]) for metric in metric_names}
    aggregate.update(
        {
            "case_count": len(case_results),
            "zero_hit_case_count": sum(case["hit_count"] == 0 for case in case_results),
            "latency_ms_p50": _percentile(all_latencies, 50),
            "latency_ms_p95": _percentile(all_latencies, 95),
            "all_rankings_deterministic": all(case["deterministic"] for case in case_results),
        }
    )
    return {"name": name, "build": build_info, "aggregate": aggregate, "cases": case_results}


def compare_methods(baseline: dict[str, Any], challenger: dict[str, Any]) -> dict[str, Any]:
    baseline_cases = {case["id"]: case for case in baseline["cases"]}
    challenger_cases = {case["id"]: case for case in challenger["cases"]}
    if set(baseline_cases) != set(challenger_cases):
        raise RuntimeError("baseline and challenger case IDs differ")
    regressions = [
        case_id
        for case_id, baseline_case in baseline_cases.items()
        if float(challenger_cases[case_id]["metrics"]["recall_at_10"]) < float(baseline_case["metrics"]["recall_at_10"])
    ]
    base_aggregate = baseline["aggregate"]
    new_aggregate = challenger["aggregate"]
    base_mrr = float(base_aggregate["mrr_at_10"])
    base_ndcg = float(base_aggregate["ndcg_at_10"])
    mrr_relative = float(new_aggregate["mrr_at_10"]) / base_mrr - 1.0 if base_mrr else None
    ndcg_relative = float(new_aggregate["ndcg_at_10"]) / base_ndcg - 1.0 if base_ndcg else None
    improves = (mrr_relative is not None and mrr_relative >= 0.05) or (
        ndcg_relative is not None and ndcg_relative >= 0.05
    )
    return {
        "recall_at_10_regressions": regressions,
        "mrr_at_10_relative_change": mrr_relative,
        "ndcg_at_10_relative_change": ndcg_relative,
        "quality_improves_by_5_percent": improves,
        "pass": not regressions and improves,
    }


def _load_baseline_method(
    path: Path,
    *,
    method: str,
    fixture_sha256: str,
    sqlite_sha256: str,
) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("fixture", {}).get("sha256") != fixture_sha256:
        raise RuntimeError("baseline fixture SHA-256 does not match")
    if value.get("corpus", {}).get("sqlite_sha256") != sqlite_sha256:
        raise RuntimeError("baseline SQLite SHA-256 does not match")
    result = value.get("methods", {}).get(method)
    if not isinstance(result, dict):
        raise ValueError(f"baseline method is missing: {method}")
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", required=True, type=Path)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--snapshot-label", required=True)
    parser.add_argument("--lexical-result", type=Path)
    parser.add_argument("--lexical-method", default="lance_icu")
    parser.add_argument("--baseline-result", type=Path)
    parser.add_argument("--baseline-method", default="dense_bge_m3")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--warmup-runs", type=int, default=1)
    parser.add_argument("--runs", type=int, default=3)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.limit < 10:
        raise ValueError("--limit must be >= 10")
    if args.warmup_runs < 0 or args.runs < 1:
        raise ValueError("--warmup-runs must be >= 0 and --runs must be >= 1")
    if args.output.exists() or args.work_dir.exists():
        raise FileExistsError("output or comparison work directory already exists")

    fixture_metadata, cases = load_fixture(args.fixture)
    fixture_sha256 = _sha256_file(args.fixture)
    sqlite_sha256 = _sha256_file(args.sqlite)
    conn = open_sqlite_read_only(args.sqlite)
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity_check failed: {integrity}")
    finally:
        conn.close()

    manifest = _validate_manifest(
        args.manifest,
        artifact=args.artifact,
        fixture_sha256=fixture_sha256,
        sqlite_sha256=sqlite_sha256,
    )
    artifact = _load_artifact(
        args.artifact,
        expected_query_ids=[case.case_id for case in cases],
    )
    if int(manifest["artifact"]["dimension"]) != int(artifact["document_vectors"].shape[1]):
        raise RuntimeError("embedding dimension differs from manifest")
    if int(manifest["corpus"]["chunk_count"]) != len(artifact["chunk_ids"]):
        raise RuntimeError("embedding chunk count differs from manifest")

    table, build_info = _build_lance_table(artifact, args.work_dir)
    profile = str(manifest["profile"])
    dense_name = f"dense_{profile}"
    query_vectors = {case.case_id: artifact["query_vectors"][index] for index, case in enumerate(cases)}

    def dense_search(case: EvalCase, limit: int) -> list[SearchHit]:
        return _dense_search(
            table,
            query_vectors[case.case_id],
            case,
            limit=limit,
            max_chunks_per_page=int(build_info["max_chunks_per_page"]),
        )

    dense_result = evaluate_method(
        dense_name,
        cases,
        dense_search,
        limit=args.limit,
        warmup_runs=args.warmup_runs,
        measured_runs=args.runs,
        build_info=build_info,
    )
    methods = {dense_name: dense_result}

    lexical_source: dict[str, Any] | None = None
    if args.lexical_result is not None:
        lexical_rankings, lexical_method_result = _load_lexical_rankings(
            args.lexical_result,
            method=args.lexical_method,
            fixture_sha256=fixture_sha256,
        )
        if set(lexical_rankings) != {case.case_id for case in cases}:
            raise RuntimeError("lexical and dense case IDs differ")
        hybrid_name = f"{args.lexical_method}_{profile}_rrf"

        def hybrid_search(case: EvalCase, limit: int) -> list[SearchHit]:
            return reciprocal_rank_fusion(
                [lexical_rankings[case.case_id][:limit], dense_search(case, limit)],
                limit=limit,
            )

        methods[hybrid_name] = evaluate_method(
            hybrid_name,
            cases,
            hybrid_search,
            limit=args.limit,
            warmup_runs=args.warmup_runs,
            measured_runs=args.runs,
            build_info={
                "build_seconds": 0.0,
                "uses": [args.lexical_method, dense_name],
                "k_rrf": 60,
            },
        )
        lexical_source = {
            "file_name": args.lexical_result.name,
            "sha256": _sha256_file(args.lexical_result),
            "method": args.lexical_method,
            "aggregate": lexical_method_result["aggregate"],
        }

    comparison: dict[str, Any] | None = None
    if args.baseline_result is not None:
        baseline = _load_baseline_method(
            args.baseline_result,
            method=args.baseline_method,
            fixture_sha256=fixture_sha256,
            sqlite_sha256=sqlite_sha256,
        )
        comparison = {
            "baseline_file_name": args.baseline_result.name,
            "baseline_sha256": _sha256_file(args.baseline_result),
            "baseline_method": args.baseline_method,
            "challenger_method": dense_name,
            **compare_methods(baseline, dense_result),
        }

    sqlite_sha256_after = _sha256_file(args.sqlite)
    if sqlite_sha256_after != sqlite_sha256:
        raise RuntimeError("source SQLite changed during dense evaluation")
    relevant_pages = {key for case in cases for key in case.relevant}
    indexed_pages = {
        PageKey(str(book), int(page)) for book, page in zip(artifact["book_names"], artifact["page_nos"], strict=True)
    }
    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "snapshot_label": args.snapshot_label,
        "fixture": {
            "file_name": args.fixture.name,
            "sha256": fixture_sha256,
            "case_count": len(cases),
            "metadata": {key: value for key, value in fixture_metadata.items() if key not in {"cases"}},
        },
        "corpus": {
            "sqlite_file_name": args.sqlite.name,
            "sqlite_sha256": sqlite_sha256,
            "integrity_check": "ok",
            "indexed_chunks": len(artifact["chunk_ids"]),
            "indexed_pages": len(indexed_pages),
            "relevant_page_refs": sum(len(case.relevant) for case in cases),
            "relevant_unique_pages": len(relevant_pages),
            "relevant_unique_pages_missing_from_dense_corpus": [
                {"book_name": key.book_name, "page_no": key.page_no} for key in sorted(relevant_pages - indexed_pages)
            ],
        },
        "embedding": {
            "manifest_file_name": args.manifest.name,
            "manifest_sha256": _sha256_file(args.manifest),
            "artifact_file_name": args.artifact.name,
            "artifact_sha256": _sha256_file(args.artifact),
            "profile": profile,
            "model": manifest["model"],
            "runtime": manifest["runtime"],
        },
        "lexical_source": lexical_source,
        "protocol": {
            "metric": "cosine",
            "search_mode": "exact",
            "limit": args.limit,
            "warmup_runs": args.warmup_runs,
            "measured_runs": args.runs,
            "page_score": "best matching chunk",
            "result_contains_source_text": False,
        },
        "methods": methods,
        "comparison_to_bge_m3": comparison,
        "safety": {
            "sqlite_sha256_before": sqlite_sha256,
            "sqlite_sha256_after": sqlite_sha256_after,
            "source_text_in_result": False,
            "embedding_in_result": False,
            "production_paths_modified": False,
        },
    }
    _write_json(args.output, result)
    print(
        json.dumps(
            {
                "event": "complete",
                "output": str(args.output),
                "work_dir": str(args.work_dir),
                "profile": profile,
                "aggregates": {name: method["aggregate"] for name, method in methods.items()},
                "comparison_to_bge_m3": comparison,
                "dense_corpus_missing_relevant_pages": len(relevant_pages - indexed_pages),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
