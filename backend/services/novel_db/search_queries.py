"""検索接続を受け取り候補・ページ人物を取得するadapter。接続生成と順位統合は行わない。"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lancedb.table import Table


def query_fts_rows(
    conn: sqlite3.Connection,
    or_query: str,
    book_names: list[str] | None,
    top: int,
    *,
    min_chars: int,
    body_page_margin: int,
) -> list[tuple]:
    sql = """
        SELECT b.name, p.page_no,
               snippet(pages_fts, 0, '<mark>', '</mark>', '…', 32) AS snippet,
               bm25(pages_fts) AS score
        FROM pages_fts
        JOIN pages p ON pages_fts.rowid = p.id
        JOIN books b ON p.book_id = b.id
        WHERE pages_fts MATCH ?
          AND p.index_eligible = 1
          AND p.char_count >= ?
          AND p.page_no > ?
          AND p.page_no <= b.page_count - ?
    """
    params: list = [or_query, min_chars, body_page_margin, body_page_margin]
    if book_names is not None:
        placeholders = ",".join(["?"] * len(book_names))
        sql += f" AND b.name IN ({placeholders})"
        params.extend(book_names)
    sql += " ORDER BY score ASC, p.id ASC LIMIT ?"
    params.append(top)

    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []


def query_vector_rows(
    table: Table,
    emb: list[float],
    book_names: list[str] | None,
    top: int,
    *,
    min_chars: int,
    body_page_margin: int,
) -> list[tuple]:
    has_extra_filter = min_chars > 0 or body_page_margin > 0 or book_names is not None
    k = max(top * 5, 50) if has_extra_filter else top

    query_builder = (
        table.search(emb).limit(k).select(["chunk_id", "book_name", "page_no", "text", "char_count", "page_count"])
    )

    filters: list[str] = []
    if min_chars > 0:
        filters.append(f"char_count >= {min_chars}")
    if book_names is not None:
        quoted = ", ".join(f"'{n}'" for n in book_names)
        filters.append(f"book_name IN ({quoted})")
    if filters:
        query_builder = query_builder.where(" AND ".join(filters), prefilter=True)

    results = query_builder.to_list()

    if body_page_margin > 0:
        results = [
            r
            for r in results
            if r["page_no"] > body_page_margin and r["page_no"] <= (r["page_count"] - body_page_margin)
        ]

    results.sort(key=lambda r: r["_distance"])
    rows: list[tuple] = [(r["book_name"], r["page_no"], r["text"], r["_distance"]) for r in results[:top]]
    return rows


def fetch_main_characters(conn: sqlite3.Connection, keys: list[tuple[str, int]]) -> dict[tuple[str, int], list[str]]:
    """指定された (book_name, page_no) の組に対して main_characters を一括取得する。"""
    if not keys:
        return {}
    cols = {row[1] for row in conn.execute("PRAGMA table_info(pages)").fetchall()}
    if "main_characters" not in cols:
        return {}
    placeholders = " OR ".join(["(b.name = ? AND p.page_no = ?)"] * len(keys))
    params: list = []
    for book, page in keys:
        params.extend([book, page])
    sql = f"""
        SELECT b.name, p.page_no, p.main_characters
        FROM pages p
        JOIN books b ON p.book_id = b.id
        WHERE {placeholders}
    """
    result: dict[tuple[str, int], list[str]] = {}
    for book_name, page_no, raw in conn.execute(sql, params):
        if raw is None or raw == "":
            result[(book_name, page_no)] = []
        else:
            result[(book_name, page_no)] = [n.strip() for n in raw.split(",") if n.strip()]
    return result
