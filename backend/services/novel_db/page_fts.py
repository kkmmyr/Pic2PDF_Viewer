"""SQLite pagesを正本とする世代別LanceDB ICU全文検索。"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

import lancedb
import pyarrow as pa
from lancedb.index import FTS
from lancedb.query import FullTextOperator, MatchQuery
from lancedb.table import Table

from utils.logger import get_logger

from .lance_store import get_db
from .search_scope import Scope
from .search_scope import resolve_book_names as _resolve_book_names

logger = get_logger(__name__)

PAGE_FTS_STATE_KEY = "page_icu"
PAGE_FTS_INDEX_NAME = "page_icu_fts"
PAGE_FTS_INDEX_CONFIG: dict[str, object] = {
    "name": PAGE_FTS_INDEX_NAME,
    "column": "text",
    "base_tokenizer": "icu",
    "with_position": False,
    "language": "English",
    "max_token_length": 40,
    "lower_case": True,
    "stem": False,
    "remove_stop_words": False,
    "ascii_folding": False,
    "query_operator": "OR",
}

_TABLE_NAME_RE = re.compile(r"^pages_icu_r\d+_[0-9a-f]{12}_\d+$")
_QUERY_TOKEN_RE = re.compile(r"[ぁ-んァ-ヴー一-龯々ヶa-zA-Z0-9]+")
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


class PageFtsUnavailable(RuntimeError):
    """ICU索引を安全に検索できない状態。呼び出し側はFTS5へ縮退できる。"""


class PageFtsBuildError(RuntimeError):
    """ICU索引の構築または公開前検証に失敗した。"""


class PageFtsBuildConflict(PageFtsBuildError):
    """構築中にSQLite本文世代が変わり、active化を拒否した。"""


@dataclass(frozen=True)
class PageFtsState:
    index_name: str
    source_revision: int
    active_source_revision: int | None
    active_table_name: str | None
    source_sha256: str | None
    row_count: int | None
    status: str
    built_at: str | None
    lancedb_version: str | None


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
class _PageRow:
    page_id: int
    book_id: int
    book_name: str
    page_no: int
    text: str
    char_count: int
    page_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def get_page_fts_state(conn: sqlite3.Connection) -> PageFtsState | None:
    """page ICU索引のSQLite状態を返す。migration未適用時は例外をそのまま返す。"""
    row = conn.execute(
        """
        SELECT index_name, source_revision, active_source_revision, active_table_name,
               source_sha256, row_count, status, built_at, lancedb_version
        FROM novel_search_index_state
        WHERE index_name = ?
        """,
        (PAGE_FTS_STATE_KEY,),
    ).fetchone()
    if row is None:
        return None
    return PageFtsState(
        index_name=str(row[0]),
        source_revision=int(row[1]),
        active_source_revision=int(row[2]) if row[2] is not None else None,
        active_table_name=str(row[3]) if row[3] is not None else None,
        source_sha256=str(row[4]) if row[4] is not None else None,
        row_count=int(row[5]) if row[5] is not None else None,
        status=str(row[6]),
        built_at=str(row[7]) if row[7] is not None else None,
        lancedb_version=str(row[8]) if row[8] is not None else None,
    )


def mark_page_fts_stale(conn: sqlite3.Connection) -> None:
    """canonical pages変更と同じtransactionでsource世代を進める。commitは呼び出し側責務。"""
    conn.execute(
        """
        INSERT INTO novel_search_index_state (index_name, source_revision, status)
        VALUES (?, 1, 'stale')
        ON CONFLICT(index_name) DO UPDATE SET
            source_revision = novel_search_index_state.source_revision + 1,
            status = 'stale'
        """,
        (PAGE_FTS_STATE_KEY,),
    )


def _load_source_rows(conn: sqlite3.Connection) -> list[_PageRow]:
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
        _PageRow(
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


def _source_sha256(rows: Sequence[_PageRow]) -> str:
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


def _rows_from_arrow(data: pa.Table) -> list[_PageRow]:
    return [
        _PageRow(
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


def _validate_built_table(
    table: Table,
    source_rows: Sequence[_PageRow],
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


def _activate_index(
    conn: sqlite3.Connection,
    *,
    source_revision: int,
    table_name: str,
    source_sha256: str,
    row_count: int,
    lancedb_version: str,
) -> str:
    with conn:
        cursor = conn.execute(
            """
            UPDATE novel_search_index_state
            SET active_source_revision = ?, active_table_name = ?, source_sha256 = ?,
                row_count = ?, status = 'active', built_at = datetime('now', '+9 hours'),
                lancedb_version = ?
            WHERE index_name = ? AND source_revision = ?
            """,
            (
                source_revision,
                table_name,
                source_sha256,
                row_count,
                lancedb_version,
                PAGE_FTS_STATE_KEY,
                source_revision,
            ),
        )
        if cursor.rowcount != 1:
            raise PageFtsBuildConflict("SQLite pages changed while the ICU index was being built")
        row = conn.execute(
            "SELECT built_at FROM novel_search_index_state WHERE index_name = ?",
            (PAGE_FTS_STATE_KEY,),
        ).fetchone()
        if row is None or row[0] is None:
            raise PageFtsBuildError("active page FTS state could not be read back")
        return str(row[0])


def _drop_failed_table(table_name: str) -> None:
    if not _TABLE_NAME_RE.fullmatch(table_name):
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


def _validate_active_table(table: Table, state: PageFtsState) -> None:
    if state.row_count is None or table.count_rows() != state.row_count:
        raise PageFtsUnavailable("active ICU table row count mismatch")
    indices = [index for index in table.list_indices() if index.name == PAGE_FTS_INDEX_NAME]
    if len(indices) != 1:
        raise PageFtsUnavailable("active ICU FTS index is missing")
    index = indices[0]
    details = index.index_details or {}
    if index.index_type != "FTS" or details.get("base_tokenizer") != "icu":
        raise PageFtsUnavailable("active ICU FTS index has unexpected configuration")
    if any(details.get(key) is not False for key in ("stem", "remove_stop_words", "ascii_folding")):
        raise PageFtsUnavailable("active ICU FTS index normalization settings are unexpected")
    if details.get("with_position") is not False or details.get("lower_case") is not True:
        raise PageFtsUnavailable("active ICU FTS index token settings are unexpected")
    if details.get("max_token_length") != 40:
        raise PageFtsUnavailable("active ICU FTS index max token length is unexpected")
    stats = table.index_stats(PAGE_FTS_INDEX_NAME)
    if stats is None or stats.num_indexed_rows != state.row_count or stats.num_unindexed_rows != 0:
        raise PageFtsUnavailable("active ICU FTS index is incomplete")


def _open_active_table(conn: sqlite3.Connection) -> tuple[Table, PageFtsState]:
    state = get_page_fts_state(conn)
    if state is None:
        raise PageFtsUnavailable("page ICU state is missing")
    if state.status != "active" or state.active_source_revision != state.source_revision:
        raise PageFtsUnavailable("page ICU index is missing or stale")
    if state.active_table_name is None or not _TABLE_NAME_RE.fullmatch(state.active_table_name):
        raise PageFtsUnavailable("active page ICU table name is invalid")
    if state.source_sha256 is None or state.active_source_revision is None:
        raise PageFtsUnavailable("active page ICU manifest is incomplete")
    expected_prefix = f"pages_icu_r{state.active_source_revision}_{state.source_sha256[:12]}_"
    if not state.active_table_name.startswith(expected_prefix):
        raise PageFtsUnavailable("active page ICU table does not match its manifest")
    current_version = str(getattr(lancedb, "__version__", "unknown"))
    if state.lancedb_version != current_version:
        raise PageFtsUnavailable("page ICU index was built with a different LanceDB version")
    try:
        table = get_db().open_table(state.active_table_name)
        _validate_active_table(table, state)
    except PageFtsUnavailable:
        raise
    except Exception as exc:
        raise PageFtsUnavailable("active page ICU table could not be opened") from exc
    return table, state


def _scope_book_ids(conn: sqlite3.Connection, scope: Scope) -> set[int] | None:
    book_names = _resolve_book_names(scope)
    if book_names is None:
        return None
    if not book_names:
        return set()
    placeholders = ",".join("?" for _ in book_names)
    rows = conn.execute(
        f"SELECT id FROM books WHERE name IN ({placeholders})",
        list(book_names),
    ).fetchall()
    return {int(row[0]) for row in rows}


def _query_fragments(query: str) -> list[str]:
    candidates: list[str] = []
    for token in _QUERY_TOKEN_RE.findall(query):
        token = token[:128]
        candidates.append(token)
        for width in range(min(12, len(token) - 1), 1, -1):
            candidates.extend(token[start : start + width] for start in range(len(token) - width + 1))
    return sorted(set(candidates), key=lambda value: (-len(value), value))


def build_page_fts_snippet(text: str, query: str, max_chars: int = 200) -> str:
    """ICU offset非公開のため、query中の最長一致断片を中心にraw snippetを作る。"""
    if max_chars < 1:
        return ""
    match_start = -1
    match_text = ""
    folded_text = text.casefold()
    for fragment in _query_fragments(query):
        start = text.find(fragment)
        if start < 0:
            start = folded_text.find(fragment.casefold())
        if start >= 0:
            match_start = start
            match_text = text[start : start + len(fragment)]
            break

    if match_start < 0:
        suffix = "…" if len(text) > max_chars else ""
        return text[:max_chars] + suffix

    available = max(max_chars - len(match_text), 0)
    start = max(match_start - available // 2, 0)
    end = min(start + max_chars, len(text))
    start = max(end - max_chars, 0)
    before = text[start:match_start]
    after_start = match_start + len(match_text)
    after = text[after_start:end]
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{before}<mark>{match_text}</mark>{after}{suffix}"


def _fetch_canonical_pages(conn: sqlite3.Connection, page_ids: list[int]) -> dict[int, sqlite3.Row]:
    if not page_ids:
        return {}
    placeholders = ",".join("?" for _ in page_ids)
    rows = conn.execute(
        f"""
        SELECT p.id, p.book_id, b.name, p.page_no, p.full_text, p.char_count,
               b.page_count, p.index_eligible
        FROM pages p
        JOIN books b ON p.book_id = b.id
        WHERE p.id IN ({placeholders})
        """,
        page_ids,
    ).fetchall()
    return {int(row[0]): row for row in rows}


def search_page_fts(
    conn: sqlite3.Connection,
    query: str,
    scope: Scope,
    top: int = 30,
    *,
    min_chars: int = 0,
    body_page_margin: int = 0,
) -> list[tuple[str, int, str, float]]:
    """active ICU索引を検索し、canonical SQLite本文からFTS互換tupleを返す。"""
    if top <= 0 or not query.strip():
        return []
    book_ids = _scope_book_ids(conn, scope)
    if book_ids == set():
        return []

    table, _state = _open_active_table(conn)
    builder = table.search(
        MatchQuery(
            query,
            "text",
            boost=1.0,
            fuzziness=0,
            max_expansions=50,
            operator=FullTextOperator.OR,
            prefix_length=0,
        ),
        query_type="fts",
    )
    filters: list[str] = []
    if book_ids is not None:
        filters.append(f"book_id IN ({', '.join(str(book_id) for book_id in sorted(book_ids))})")
    if min_chars > 0:
        filters.append(f"char_count >= {int(min_chars)}")
    if body_page_margin > 0:
        margin = int(body_page_margin)
        filters.extend([f"page_no > {margin}", f"page_no <= page_count - {margin}"])
    if filters:
        builder = builder.where(" AND ".join(filters), prefilter=True)
    lance_rows: list[dict[str, Any]] = builder.limit(top).select(["page_id", "book_id", "page_no", "_score"]).to_list()
    page_ids = [int(row["page_id"]) for row in lance_rows]
    canonical = _fetch_canonical_pages(conn, page_ids)
    if len(canonical) != len(set(page_ids)):
        raise PageFtsUnavailable("active ICU hits do not match canonical SQLite pages")

    results: list[tuple[str, int, str, float]] = []
    for row in lance_rows:
        page_id = int(row["page_id"])
        source = canonical[page_id]
        book_id = int(source[1])
        page_no = int(source[3])
        char_count = int(source[5] or 0)
        page_count = int(source[6] or 0)
        if not bool(source[7]) or int(row["book_id"]) != book_id or int(row["page_no"]) != page_no:
            raise PageFtsUnavailable("active ICU hit metadata differs from canonical SQLite")
        if book_ids is not None and book_id not in book_ids:
            raise PageFtsUnavailable("active ICU scope filter returned an out-of-scope page")
        if char_count < min_chars:
            raise PageFtsUnavailable("active ICU char filter returned an ineligible page")
        if body_page_margin > 0 and not (page_no > body_page_margin and page_no <= page_count - body_page_margin):
            raise PageFtsUnavailable("active ICU page margin returned an ineligible page")
        text = str(source[4] or "")
        results.append(
            (
                str(source[2]),
                page_no,
                build_page_fts_snippet(text, query),
                float(row["_score"]),
            )
        )
    return results


__all__ = [
    "PAGE_FTS_INDEX_NAME",
    "PAGE_FTS_INDEX_CONFIG",
    "PAGE_FTS_STATE_KEY",
    "PageFtsBuildConflict",
    "PageFtsBuildError",
    "PageFtsBuildResult",
    "PageFtsState",
    "PageFtsUnavailable",
    "build_page_fts_index",
    "build_page_fts_snippet",
    "get_page_fts_state",
    "mark_page_fts_stale",
    "search_page_fts",
]
