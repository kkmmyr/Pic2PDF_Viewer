"""active page-level ICU索引の検索とcanonical SQLite再照合。"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from lancedb.query import FullTextOperator, MatchQuery
from lancedb.table import Table

from .page_fts_state import PageFtsUnavailable, open_active_page_fts_table
from .search_scope import Scope
from .search_scope import resolve_book_names as _resolve_book_names

_QUERY_TOKEN_RE = re.compile(r"[ぁ-んァ-ヴー一-龯々ヶa-zA-Z0-9]+")


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


def _search_filters(
    book_ids: set[int] | None,
    *,
    min_chars: int,
    body_page_margin: int,
) -> list[str]:
    filters: list[str] = []
    if book_ids is not None:
        filters.append(f"book_id IN ({', '.join(str(book_id) for book_id in sorted(book_ids))})")
    if min_chars > 0:
        filters.append(f"char_count >= {int(min_chars)}")
    if body_page_margin > 0:
        margin = int(body_page_margin)
        filters.extend([f"page_no > {margin}", f"page_no <= page_count - {margin}"])
    return filters


def _search_lance_rows(
    table: Table,
    query: str,
    book_ids: set[int] | None,
    *,
    top: int,
    min_chars: int,
    body_page_margin: int,
) -> list[dict[str, Any]]:
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
    filters = _search_filters(
        book_ids,
        min_chars=min_chars,
        body_page_margin=body_page_margin,
    )
    if filters:
        builder = builder.where(" AND ".join(filters), prefilter=True)
    return builder.limit(top).select(["page_id", "book_id", "page_no", "_score"]).to_list()


def _validated_result(
    row: dict[str, Any],
    source: sqlite3.Row,
    *,
    query: str,
    book_ids: set[int] | None,
    min_chars: int,
    body_page_margin: int,
) -> tuple[str, int, str, float]:
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
    return (
        str(source[2]),
        page_no,
        build_page_fts_snippet(text, query),
        float(row["_score"]),
    )


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

    table, _state = open_active_page_fts_table(conn)
    lance_rows = _search_lance_rows(
        table,
        query,
        book_ids,
        top=top,
        min_chars=min_chars,
        body_page_margin=body_page_margin,
    )
    page_ids = [int(row["page_id"]) for row in lance_rows]
    canonical = _fetch_canonical_pages(conn, page_ids)
    if len(canonical) != len(set(page_ids)):
        raise PageFtsUnavailable("active ICU hits do not match canonical SQLite pages")
    return [
        _validated_result(
            row,
            canonical[int(row["page_id"])],
            query=query,
            book_ids=book_ids,
            min_chars=min_chars,
            body_page_margin=body_page_margin,
        )
        for row in lance_rows
    ]
