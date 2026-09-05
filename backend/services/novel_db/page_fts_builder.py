"""canonical SQLite pagesからpage-level ICU索引を完全再構築する。"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass

import lancedb
import pyarrow as pa
from lancedb.index import FTS
from lancedb.table import Table

from .lance_store import get_db
from .page_fts_state import (
    PAGE_FTS_INDEX_CONFIG,
    PAGE_FTS_INDEX_NAME,
    PageFtsBuildError,
    _activate_index,
    get_page_fts_state,
    is_page_fts_table_name,
    logger,
)

_PAGE_FTS_SCHEMA = pa.schema(
    [
        pa.field("page_id", pa.int64()),
        pa.field("book_id", pa.int64()),
        pa.field("book_name", pa.utf8()),
        pa.field("page_no", pa.int32()),
        pa.field("text", pa.utf8()),
        pa.field("char_count", pa.int32()),
        pa.field("page_count", pa.int32()),
    ]
)


@dataclass(frozen=True)
class PageFtsBuildResult:
    table_name: str
    source_revision: int
    row_count: int
    source_sha256: str
    built_at: str
    lancedb_version: str

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "index_config": dict(PAGE_FTS_INDEX_CONFIG)}


@dataclass(frozen=True)
class PageFtsRow:
    page_id: int
    book_id: int
    book_name: str
    page_no: int
    text: str
    char_count: int
    page_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _load_source_rows(conn: sqlite3.Connection) -> list[PageFtsRow]:
    rows = conn.execute(
        """
        SELECT p.id, b.id, b.name, p.page_no, p.full_text, p.char_count, b.page_count
        FROM pages p
        JOIN books b ON p.book_id = b.id
        WHERE p.index_eligible = 1
        ORDER BY p.id
        """
    ).fetchall()
    return [
        PageFtsRow(
            page_id=int(row[0]),
            book_id=int(row[1]),
            book_name=str(row[2]),
            page_no=int(row[3]),
            text=str(row[4] or ""),
            char_count=int(row[5] or 0),
            page_count=int(row[6] or 0),
        )
        for row in rows
    ]


def _source_sha256(rows: Sequence[PageFtsRow]) -> str:
    digest = hashlib.sha256(b"pic2pdf-page-icu-v1\0")
    for row in rows:
        fields: tuple[object, ...] = (
            row.page_id,
            row.book_id,
            row.book_name,
            row.page_no,
            row.text,
            row.char_count,
            row.page_count,
        )
        for value in fields:
            encoded = str(value).encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
    return digest.hexdigest()


def _rows_from_arrow(data: pa.Table) -> list[PageFtsRow]:
    return [
        PageFtsRow(
            page_id=int(row["page_id"]),
            book_id=int(row["book_id"]),
            book_name=str(row["book_name"]),
            page_no=int(row["page_no"]),
            text=str(row["text"] or ""),
            char_count=int(row["char_count"] or 0),
            page_count=int(row["page_count"] or 0),
        )
        for row in data.to_pylist()
    ]


def _validate_table_rows(
    table: Table,
    source_rows: Sequence[PageFtsRow],
    source_sha256: str,
) -> None:
    expected_count = len(source_rows)
    page_ids = [row.page_id for row in source_rows]
    if len(page_ids) != len(set(page_ids)):
        raise PageFtsBuildError("source page IDs are not unique")
    if table.count_rows() != expected_count:
        raise PageFtsBuildError("LanceDB row count does not match SQLite source")
    stored_rows = sorted(_rows_from_arrow(table.to_arrow()), key=lambda row: row.page_id)
    if len({row.page_id for row in stored_rows}) != expected_count:
        raise PageFtsBuildError("LanceDB page IDs are not unique")
    if _source_sha256(stored_rows) != source_sha256:
        raise PageFtsBuildError("LanceDB content hash does not match SQLite source")


def _validate_fts_index(table: Table, expected_count: int) -> None:
    indices = [index for index in table.list_indices() if index.name == PAGE_FTS_INDEX_NAME]
    if len(indices) != 1:
        raise PageFtsBuildError("expected exactly one ICU FTS index")
    index = indices[0]
    details = index.index_details or {}
    if index.index_type != "FTS" or list(index.columns) != ["text"]:
        raise PageFtsBuildError("unexpected page FTS index type or columns")
    if details.get("base_tokenizer") != "icu":
        raise PageFtsBuildError("page FTS index is not using the ICU tokenizer")
    if any(details.get(key) is not False for key in ("stem", "remove_stop_words", "ascii_folding")):
        raise PageFtsBuildError("page FTS index normalization settings differ from the contract")
    if details.get("with_position") is not False or details.get("lower_case") is not True:
        raise PageFtsBuildError("page FTS index token settings differ from the contract")
    if details.get("max_token_length") != 40:
        raise PageFtsBuildError("page FTS index max token length differs from the contract")
    stats = table.index_stats(PAGE_FTS_INDEX_NAME)
    if stats is None:
        raise PageFtsBuildError("page FTS index statistics are unavailable")
    if stats.num_indexed_rows != expected_count or stats.num_unindexed_rows != 0:
        raise PageFtsBuildError("page FTS index contains unindexed or missing rows")


def _validate_built_table(
    table: Table,
    source_rows: Sequence[PageFtsRow],
    source_sha256: str,
) -> None:
    _validate_table_rows(table, source_rows, source_sha256)
    _validate_fts_index(table, len(source_rows))


def _drop_failed_table(table_name: str) -> None:
    if not is_page_fts_table_name(table_name):
        return
    try:
        get_db().drop_table(table_name)
    except Exception:
        logger.warning("failed to remove incomplete page ICU table: %s", table_name)


def build_page_fts_index(conn: sqlite3.Connection) -> PageFtsBuildResult:
    """全eligible pageからimmutableなICU indexを作り、整合時だけactive化する。"""
    state = get_page_fts_state(conn)
    if state is None:
        raise PageFtsBuildError("page FTS state is missing; run Alembic migrations first")

    source_revision = state.source_revision
    source_rows = _load_source_rows(conn)
    source_hash = _source_sha256(source_rows)
    table_name = f"pages_icu_r{source_revision}_{source_hash[:12]}_{time.time_ns()}"
    version = str(getattr(lancedb, "__version__", "unknown"))
    data = pa.Table.from_pylist([row.to_dict() for row in source_rows], schema=_PAGE_FTS_SCHEMA)
    created = False
    activated = False

    logger.info(
        "page ICU index build start: revision=%d rows=%d table=%s",
        source_revision,
        len(source_rows),
        table_name,
    )
    try:
        table = get_db().create_table(table_name, data=data)
        created = True
        table.create_index(
            "text",
            config=FTS(
                with_position=False,
                base_tokenizer="icu",
                language="English",
                max_token_length=40,
                lower_case=True,
                stem=False,
                remove_stop_words=False,
                ascii_folding=False,
            ),
            name=PAGE_FTS_INDEX_NAME,
            replace=False,
        )
        _validate_built_table(table, source_rows, source_hash)
        built_at = _activate_index(
            conn,
            source_revision=source_revision,
            table_name=table_name,
            source_sha256=source_hash,
            row_count=len(source_rows),
            lancedb_version=version,
        )
        activated = True
    finally:
        if created and not activated:
            _drop_failed_table(table_name)

    logger.info(
        "page ICU index build finished: revision=%d rows=%d table=%s",
        source_revision,
        len(source_rows),
        table_name,
    )
    return PageFtsBuildResult(
        table_name=table_name,
        source_revision=source_revision,
        row_count=len(source_rows),
        source_sha256=source_hash,
        built_at=built_at,
        lancedb_version=version,
    )
