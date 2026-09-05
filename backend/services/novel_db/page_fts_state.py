"""page-level ICU索引のSQLite世代状態とactive table検証。"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

import lancedb
from lancedb.table import Table

from utils.logger import get_logger

from .lance_store import get_db

logger = get_logger("services.novel_db.page_fts")

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


def is_page_fts_table_name(table_name: str) -> bool:
    return _TABLE_NAME_RE.fullmatch(table_name) is not None


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


def open_active_page_fts_table(conn: sqlite3.Connection) -> tuple[Table, PageFtsState]:
    state = get_page_fts_state(conn)
    if state is None:
        raise PageFtsUnavailable("page ICU state is missing")
    if state.status != "active" or state.active_source_revision != state.source_revision:
        raise PageFtsUnavailable("page ICU index is missing or stale")
    if state.active_table_name is None or not is_page_fts_table_name(state.active_table_name):
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
