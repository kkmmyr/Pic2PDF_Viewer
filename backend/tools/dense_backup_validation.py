"""Novel DB SQLite chunks と LanceDB の dense index を照合する検証処理。"""

from __future__ import annotations

import math
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

_DENSE_EMBEDDING_DIM = 1024
_DENSE_METADATA_FIELDS = ("book_name", "page_no", "text", "char_count", "page_count")
_DenseMetadata = tuple[str, int, str, int, int]


def _sqlite_dense_chunks(path: Path) -> dict[int, _DenseMetadata] | None:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        has_chunks = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunks'").fetchone()
        if has_chunks is None:
            return None
        rows = connection.execute(
            """
            SELECT c.id, b.name, p.page_no, c.text, p.char_count, b.page_count
            FROM chunks c
            JOIN pages p ON p.id = c.page_id
            JOIN books b ON b.id = p.book_id
            ORDER BY c.id
            """
        ).fetchall()
    finally:
        connection.close()
    return {int(row[0]): (str(row[1]), int(row[2]), str(row[3]), int(row[4]), int(row[5])) for row in rows}


def _dense_error(message: str) -> RuntimeError:
    return RuntimeError(f"dense chunk cross-store validation failed: {message}")


def _load_lance_rows(lance_db: Path, expected: dict[int, _DenseMetadata]) -> list[dict[str, Any]]:
    import lancedb

    database = lancedb.connect(lance_db)
    if "chunks" not in set(database.list_tables(limit=10_000).tables):
        if expected:
            raise _dense_error(f"LanceDB chunks table is missing for {len(expected)} SQLite rows")
        return []
    table = database.open_table("chunks").to_arrow()
    required = {"chunk_id", *_DENSE_METADATA_FIELDS, "embedding"}
    missing_columns = sorted(required - set(table.column_names))
    if missing_columns:
        raise _dense_error(f"LanceDB chunks columns are missing: {missing_columns}")
    return table.select(["chunk_id", *_DENSE_METADATA_FIELDS, "embedding"]).to_pylist()


def _validate_ids(expected: dict[int, _DenseMetadata], rows: list[dict[str, Any]]) -> set[int]:
    ids = [int(row["chunk_id"]) for row in rows]
    duplicate_ids = sorted(chunk_id for chunk_id, count in Counter(ids).items() if count > 1)
    expected_ids = set(expected)
    actual_ids = set(ids)
    missing_ids = sorted(expected_ids - actual_ids)
    extra_ids = sorted(actual_ids - expected_ids)
    if missing_ids or extra_ids or duplicate_ids:
        raise _dense_error(
            f"ID mismatch: missing={missing_ids[:10]}, extra={extra_ids[:10]}, duplicates={duplicate_ids[:10]}"
        )
    return actual_ids


def _valid_embedding(embedding: object) -> bool:
    return (
        isinstance(embedding, list)
        and len(embedding) == _DENSE_EMBEDDING_DIM
        and all(math.isfinite(float(value)) for value in embedding)
    )


def _row_mismatches(expected: dict[int, _DenseMetadata], rows: list[dict[str, Any]]) -> tuple[list[int], list[int]]:
    metadata_mismatches: list[int] = []
    invalid_vectors: list[int] = []
    for row in rows:
        chunk_id = int(row["chunk_id"])
        actual_metadata = (
            str(row["book_name"]),
            int(row["page_no"]),
            str(row["text"]),
            int(row["char_count"]),
            int(row["page_count"]),
        )
        if actual_metadata != expected[chunk_id]:
            metadata_mismatches.append(chunk_id)
        if not _valid_embedding(row["embedding"]):
            invalid_vectors.append(chunk_id)
    return metadata_mismatches, invalid_vectors


def validate_dense_chunks(novel_db: Path, lance_db: Path) -> dict[str, Any]:
    """SQLite chunksを正本としてLanceDBのID、metadata、vectorを全行検査する。"""
    expected = _sqlite_dense_chunks(novel_db)
    if expected is None:
        return {"status": "not_applicable", "reason": "sqlite_chunks_table_not_present"}
    if not lance_db.is_dir():
        if expected:
            raise _dense_error(f"LanceDB is missing for {len(expected)} SQLite rows")
        return {
            "status": "ok",
            "sqlite_rows": 0,
            "lance_rows": 0,
            "unique_ids": 0,
            "embedding_dim": _DENSE_EMBEDDING_DIM,
        }

    rows = _load_lance_rows(lance_db, expected)
    actual_ids = _validate_ids(expected, rows)
    metadata_mismatches, invalid_vectors = _row_mismatches(expected, rows)
    if metadata_mismatches:
        raise _dense_error(f"metadata mismatch for chunk IDs {metadata_mismatches[:10]}")
    if invalid_vectors:
        raise _dense_error(f"invalid embedding for chunk IDs {invalid_vectors[:10]}")
    return {
        "status": "ok",
        "sqlite_rows": len(expected),
        "lance_rows": len(rows),
        "unique_ids": len(actual_ids),
        "embedding_dim": _DENSE_EMBEDDING_DIM,
    }
