"""日本語小説検索の lexical retrieval を隔離コーパスで比較する。

本番 SQLite / LanceDB は更新しない。SQLite は read-only URI で開き、比較用の
LanceDB FTS index は ``--work-dir`` 以下へ新規作成する。結果 JSON には本文や
snippet を含めず、query、ページ参照、順位、score、集約指標だけを保存する。

使用例::

    cd backend
    uv run python scripts/eval_novel_search.py \
      --sqlite /tmp/search-eval/novel.db \
      --source-lance /tmp/search-eval/novel.lancedb \
      --snapshot-label 2026-08-22_020001 \
      --work-dir /tmp/search-eval/lexical \
      --output /tmp/search-eval/lexical-result.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import statistics
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa
from lancedb.index import FTS
from lancedb.query import MatchQuery

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from services.novel_db.search import build_fts5_or_query

SCHEMA_VERSION = 1
DEFAULT_FIXTURE = Path(__file__).with_name("fixtures") / "novel_search_eval_v1.json"
LEXICAL_METHODS = (
    "current_fts5",
    "lance_icu",
    "lance_ngram",
    "lance_icu_ngram_rrf",
)


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


def _parse_relevant(raw: object, *, case_id: str) -> dict[PageKey, int]:
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"case {case_id}: relevant must be a non-empty list")
    relevant: dict[PageKey, int] = {}
    for index, row in enumerate(raw, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"case {case_id}: relevant row {index} is not an object")
        book_name = row.get("book_name")
        page_no = row.get("page_no")
        grade = row.get("grade")
        if not isinstance(book_name, str) or not book_name.strip():
            raise ValueError(f"case {case_id}: relevant row {index} has no book_name")
        if not isinstance(page_no, int) or page_no < 0:
            raise ValueError(f"case {case_id}: relevant row {index} has invalid page_no")
        if not isinstance(grade, int) or grade < 1 or grade > 3:
            raise ValueError(f"case {case_id}: relevant row {index} has invalid grade")
        key = PageKey(book_name=book_name, page_no=page_no)
        if key in relevant:
            raise ValueError(f"case {case_id}: duplicate relevant page {key}")
        relevant[key] = grade
    return relevant


def load_fixture(path: Path) -> tuple[dict[str, Any], list[EvalCase]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("fixture root must be an object")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported fixture schema_version: {value.get('schema_version')!r}")
    raw_cases = value.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("fixture cases must be a non-empty list")

    cases: list[EvalCase] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_cases, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"case {index} is not an object")
        case_id = raw.get("id")
        query = raw.get("query")
        source = raw.get("source", "")
        scope = raw.get("scope", {"type": "all"})
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"case {index} has no id")
        if case_id in seen_ids:
            raise ValueError(f"duplicate case id: {case_id}")
        seen_ids.add(case_id)
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"case {case_id}: query is empty")
        if not isinstance(source, str):
            raise ValueError(f"case {case_id}: source must be a string")
        if not isinstance(scope, dict) or scope.get("type") not in {"all", "book"}:
            raise ValueError(f"case {case_id}: scope must be all or book")
        scope_book: str | None = None
        if scope.get("type") == "book":
            scope_book = scope.get("book_name")
            if not isinstance(scope_book, str) or not scope_book:
                raise ValueError(f"case {case_id}: book scope has no book_name")
        relevant = _parse_relevant(raw.get("relevant"), case_id=case_id)
        cases.append(
            EvalCase(
                case_id=case_id,
                query=query.strip(),
                scope_book=scope_book,
                relevant=relevant,
                source=source,
            )
        )
    metadata = {key: item for key, item in value.items() if key != "cases"}
    return metadata, cases


def open_sqlite_read_only(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"SQLite DB not found: {path}")
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def inspect_sqlite(conn: sqlite3.Connection, path: Path) -> dict[str, Any]:
    integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    counts = {
        table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in ("books", "pages", "chunks")
    }
    eligible_pages = int(conn.execute("SELECT COUNT(*) FROM pages WHERE index_eligible = 1").fetchone()[0])
    fts_row = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'pages_fts'").fetchone()
    return {
        "file_name": path.name,
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
        "integrity_check": integrity,
        "counts": counts,
        "index_eligible_pages": eligible_pages,
        "fts_definition": str(fts_row[0]) if fts_row else None,
    }


def inspect_source_lance(path: Path, conn: sqlite3.Connection) -> dict[str, Any]:
    if not path.is_dir():
        raise FileNotFoundError(f"LanceDB not found: {path}")
    db = lancedb.connect(path)
    table_names = list(db.list_tables().tables)
    table_counts = {name: int(db.open_table(name).count_rows()) for name in table_names}
    result: dict[str, Any] = {
        "directory_name": path.name,
        "table_counts": table_counts,
        "size_bytes": sum(item.stat().st_size for item in path.rglob("*") if item.is_file()),
    }
    if "chunks" not in table_names:
        result["chunks_consistency"] = {"valid": False, "reason": "chunks table is missing"}
        return result

    rows = db.open_table("chunks").search().select(["chunk_id", "book_name", "page_no"]).limit(None).to_list()
    ids = Counter(int(row["chunk_id"]) for row in rows)
    lance_ids = set(ids)
    sqlite_ids = {int(row[0]) for row in conn.execute("SELECT id FROM chunks")}
    duplicate_ids = sorted(chunk_id for chunk_id, count in ids.items() if count > 1)
    book_names = {str(row["book_name"]) for row in rows}
    valid = len(rows) == len(sqlite_ids) and len(lance_ids) == len(rows) and lance_ids == sqlite_ids
    result["chunks_consistency"] = {
        "valid": valid,
        "row_count": len(rows),
        "unique_chunk_ids": len(lance_ids),
        "duplicate_id_count": len(duplicate_ids),
        "duplicate_row_count": sum(count - 1 for count in ids.values() if count > 1),
        "duplicate_id_sample": duplicate_ids[:20],
        "indexed_book_count": len(book_names),
        "sqlite_chunk_ids_missing_from_lance": len(sqlite_ids - lance_ids),
        "lance_chunk_ids_missing_from_sqlite": len(lance_ids - sqlite_ids),
    }
    return result


def load_eligible_pages(conn: sqlite3.Connection) -> pa.Table:
    rows = conn.execute(
        """
        SELECT p.id, b.name, p.page_no, COALESCE(p.full_text, '')
        FROM pages p
        JOIN books b ON b.id = p.book_id
        WHERE p.index_eligible = 1
        ORDER BY p.id
        """
    ).fetchall()
    return pa.table(
        {
            "row_id": pa.array((int(row[0]) for row in rows), type=pa.int64()),
            "book_name": pa.array((str(row[1]) for row in rows), type=pa.string()),
            "page_no": pa.array((int(row[2]) for row in rows), type=pa.int32()),
            "text": pa.array((str(row[3]) for row in rows), type=pa.string()),
        }
    )


def _sqlite_search(conn: sqlite3.Connection, case: EvalCase, limit: int) -> list[SearchHit]:
    match_query = build_fts5_or_query(case.query)
    if not match_query:
        return []
    sql = """
        SELECT b.name, p.page_no, bm25(pages_fts) AS score
        FROM pages_fts
        JOIN pages p ON pages_fts.rowid = p.id
        JOIN books b ON p.book_id = b.id
        WHERE pages_fts MATCH ? AND p.index_eligible = 1
    """
    params: list[object] = [match_query]
    if case.scope_book is not None:
        sql += " AND b.name = ?"
        params.append(case.scope_book)
    sql += " ORDER BY score ASC, p.id ASC LIMIT ?"
    params.append(limit)
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []
    return [
        SearchHit(PageKey(book_name=str(book_name), page_no=int(page_no)), float(score))
        for book_name, page_no, score in rows
    ]


def _lance_filter(book_name: str) -> str:
    escaped = book_name.replace("'", "''")
    return f"book_name = '{escaped}'"


def _lance_search(table: Any, case: EvalCase, limit: int) -> list[SearchHit]:
    builder = table.search(MatchQuery(case.query, "text"), query_type="fts")
    if case.scope_book is not None:
        builder = builder.where(_lance_filter(case.scope_book), prefilter=True)
    rows = builder.limit(limit).select(["book_name", "page_no", "_score"]).to_list()
    return [
        SearchHit(
            PageKey(book_name=str(row["book_name"]), page_no=int(row["page_no"])),
            float(row["_score"]),
        )
        for row in rows
    ]


def build_lance_fts(
    pages: pa.Table,
    destination: Path,
    *,
    tokenizer: str,
) -> tuple[Any, dict[str, Any]]:
    if destination.exists():
        raise FileExistsError(f"comparison index already exists: {destination}")
    destination.mkdir(parents=True)
    started = time.perf_counter()
    db = lancedb.connect(destination)
    table = db.create_table("pages", data=pages)
    if tokenizer == "icu":
        config = FTS(
            base_tokenizer="icu",
            stem=False,
            remove_stop_words=False,
            ascii_folding=False,
        )
    elif tokenizer == "ngram":
        config = FTS(
            base_tokenizer="ngram",
            stem=False,
            remove_stop_words=False,
            ascii_folding=False,
            ngram_min_length=2,
            ngram_max_length=3,
        )
    else:
        raise ValueError(f"unsupported tokenizer: {tokenizer}")
    table.create_index("text", config=config, replace=True)
    build_seconds = time.perf_counter() - started
    index = table.list_indices()[0]
    info = {
        "tokenizer": tokenizer,
        "build_seconds": build_seconds,
        "directory_size_bytes": sum(item.stat().st_size for item in destination.rglob("*") if item.is_file()),
        "index_size_bytes": index.size_bytes,
        "indexed_rows": index.num_indexed_rows,
        "index_details": index.index_details,
    }
    return table, info


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


def evaluate_method(
    name: str,
    cases: Sequence[EvalCase],
    search: SearchFn,
    *,
    limit: int,
    warmup_runs: int,
    measured_runs: int,
    build_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if measured_runs < 1:
        raise ValueError("measured_runs must be >= 1")
    case_results: list[dict[str, Any]] = []
    all_latencies: list[float] = []
    metric_names = ("recall_at_5", "recall_at_10", "recall_at_30", "mrr_at_10", "ndcg_at_10")

    for case in cases:
        for _ in range(warmup_runs):
            search(case, limit)
        measured_rankings: list[list[SearchHit]] = []
        latencies: list[float] = []
        for _ in range(measured_runs):
            started = time.perf_counter()
            hits = search(case, limit)
            latencies.append((time.perf_counter() - started) * 1000.0)
            measured_rankings.append(hits)
        all_latencies.extend(latencies)
        first = measured_rankings[0]
        first_keys = [hit.key for hit in first]
        deterministic = all([hit.key for hit in ranking] == first_keys for ranking in measured_rankings[1:])
        metrics = metrics_for_ranking(first, case.relevant)
        case_results.append(
            {
                "id": case.case_id,
                "query": case.query,
                "scope": {"type": "book", "book_name": case.scope_book}
                if case.scope_book is not None
                else {"type": "all"},
                "source": case.source,
                "relevant": [
                    {"book_name": key.book_name, "page_no": key.page_no, "grade": grade}
                    for key, grade in sorted(case.relevant.items())
                ],
                "hit_count": len(first),
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
                "metrics": metrics,
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
    return {
        "name": name,
        "build": build_info or {"build_seconds": 0.0, "uses_existing_index": True},
        "aggregate": aggregate,
        "cases": case_results,
    }


def compare_to_baseline(baseline: dict[str, Any], challenger: dict[str, Any]) -> dict[str, Any]:
    baseline_cases = {case["id"]: case for case in baseline["cases"]}
    challenger_cases = {case["id"]: case for case in challenger["cases"]}
    regressions: list[str] = []
    rescues: list[str] = []
    for case_id, baseline_case in baseline_cases.items():
        challenger_case = challenger_cases[case_id]
        baseline_recall = float(baseline_case["metrics"]["recall_at_10"])
        challenger_recall = float(challenger_case["metrics"]["recall_at_10"])
        if challenger_recall < baseline_recall:
            regressions.append(case_id)
        if baseline_case["hit_count"] == 0 and challenger_recall > 0:
            rescues.append(case_id)

    baseline_aggregate = baseline["aggregate"]
    challenger_aggregate = challenger["aggregate"]
    mrr_base = float(baseline_aggregate["mrr_at_10"])
    ndcg_base = float(baseline_aggregate["ndcg_at_10"])
    return {
        "recall_at_10_regressions": regressions,
        "zero_hit_rescues": rescues,
        "mrr_at_10_delta": float(challenger_aggregate["mrr_at_10"]) - mrr_base,
        "ndcg_at_10_delta": float(challenger_aggregate["ndcg_at_10"]) - ndcg_base,
        "mrr_at_10_relative_change": (float(challenger_aggregate["mrr_at_10"]) / mrr_base - 1.0 if mrr_base else None),
        "ndcg_at_10_relative_change": (
            float(challenger_aggregate["ndcg_at_10"]) / ndcg_base - 1.0 if ndcg_base else None
        ),
        "latency_p95_under_200_ms": float(challenger_aggregate["latency_ms_p95"]) <= 200.0,
        "preliminary_gate_a_pass": (
            not regressions and bool(rescues) and float(challenger_aggregate["latency_ms_p95"]) <= 200.0
        ),
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", required=True, type=Path)
    parser.add_argument("--source-lance", type=Path)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--snapshot-label", required=True)
    parser.add_argument("--methods", nargs="+", choices=LEXICAL_METHODS, default=list(LEXICAL_METHODS))
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

    fixture_metadata, cases = load_fixture(args.fixture)
    conn = open_sqlite_read_only(args.sqlite)
    temporary: tempfile.TemporaryDirectory[str] | None = None
    try:
        sqlite_info = inspect_sqlite(conn, args.sqlite)
        if sqlite_info["integrity_check"] != "ok":
            raise RuntimeError(f"SQLite integrity_check failed: {sqlite_info['integrity_check']}")
        source_lance_info = inspect_source_lance(args.source_lance, conn) if args.source_lance else None
        pages = load_eligible_pages(conn)
        if len(pages) != sqlite_info["index_eligible_pages"]:
            raise RuntimeError("eligible page count changed while loading the isolated corpus")

        if args.work_dir is None:
            temporary = tempfile.TemporaryDirectory(prefix="pic2pdf-novel-search-")
            work_dir = Path(temporary.name)
        else:
            work_dir = args.work_dir
            work_dir.mkdir(parents=True, exist_ok=True)

        methods: dict[str, dict[str, Any]] = {}
        if "current_fts5" in args.methods:
            methods["current_fts5"] = evaluate_method(
                "current_fts5",
                cases,
                lambda case, limit: _sqlite_search(conn, case, limit),
                limit=args.limit,
                warmup_runs=args.warmup_runs,
                measured_runs=args.runs,
            )

        tables: dict[str, Any] = {}
        needs_rrf = "lance_icu_ngram_rrf" in args.methods
        for method, tokenizer in (("lance_icu", "icu"), ("lance_ngram", "ngram")):
            if method not in args.methods and not needs_rrf:
                continue
            destination = work_dir / method
            if destination.exists():
                raise FileExistsError(f"comparison index already exists: {destination}")
            table, build_info = build_lance_fts(pages, destination, tokenizer=tokenizer)
            tables[method] = table
            if method not in args.methods:
                continue
            methods[method] = evaluate_method(
                method,
                cases,
                lambda case, limit, current_table=table: _lance_search(current_table, case, limit),
                limit=args.limit,
                warmup_runs=args.warmup_runs,
                measured_runs=args.runs,
                build_info=build_info,
            )

        if needs_rrf:
            icu_table = tables["lance_icu"]
            ngram_table = tables["lance_ngram"]

            def search_rrf(case: EvalCase, limit: int) -> list[SearchHit]:
                return reciprocal_rank_fusion(
                    [
                        _lance_search(icu_table, case, limit),
                        _lance_search(ngram_table, case, limit),
                    ],
                    limit=limit,
                )

            methods["lance_icu_ngram_rrf"] = evaluate_method(
                "lance_icu_ngram_rrf",
                cases,
                search_rrf,
                limit=args.limit,
                warmup_runs=args.warmup_runs,
                measured_runs=args.runs,
                build_info={
                    "build_seconds": 0.0,
                    "uses_indexes": ["lance_icu", "lance_ngram"],
                    "k_rrf": 60,
                },
            )

        comparisons: dict[str, Any] = {}
        baseline = methods.get("current_fts5")
        if baseline is not None:
            comparisons = {
                name: compare_to_baseline(baseline, method)
                for name, method in methods.items()
                if name != "current_fts5"
            }

        result = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(UTC).isoformat(),
            "snapshot_label": args.snapshot_label,
            "fixture": {
                **fixture_metadata,
                "file_name": args.fixture.name,
                "sha256": _sha256_file(args.fixture),
                "case_count": len(cases),
                "relevant_book_count": len({key.book_name for case in cases for key in case.relevant}),
            },
            "corpus": {
                "sqlite": sqlite_info,
                "source_lance": source_lance_info,
            },
            "protocol": {
                "methods": args.methods,
                "limit": args.limit,
                "warmup_runs": args.warmup_runs,
                "measured_runs": args.runs,
                "result_contains_source_text": False,
            },
            "methods": methods,
            "comparisons_to_current_fts5": comparisons,
        }
        _write_json(args.output, result)
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "snapshot_label": args.snapshot_label,
                    "case_count": len(cases),
                    "aggregates": {name: method["aggregate"] for name, method in methods.items()},
                    "comparisons": comparisons,
                    "source_lance_consistent": (
                        source_lance_info.get("chunks_consistency", {}).get("valid")
                        if source_lance_info is not None
                        else None
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        conn.close()
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
