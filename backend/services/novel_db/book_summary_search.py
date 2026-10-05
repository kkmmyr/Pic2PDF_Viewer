"""書籍サマリ embedding を使う書籍単位の検索。"""

from __future__ import annotations

import sqlite3

from .connection import with_db
from .embedder import embed_batch
from .lance_store import get_summaries_table
from .search_scope import Scope, resolve_book_names
from .summary_repository import get_rag_ready_book_names


def search_book_summaries(
    conn: sqlite3.Connection,
    query: str,
    scope: Scope,
    *,
    top: int = 11,
) -> list[tuple[str, float]]:
    """書籍サマリをベクトル検索し、距離の昇順で返す。"""
    book_names = get_rag_ready_book_names(conn, resolve_book_names(scope))
    if not book_names:
        return []

    table = get_summaries_table()
    if table.count_rows() == 0:
        return []

    embedding = embed_batch([query])[0]
    quoted = ", ".join("'" + name.replace("'", "''") + "'" for name in book_names)
    query_builder = (
        table.search(embedding).limit(top).select(["book_name"]).where(f"book_name IN ({quoted})", prefilter=True)
    )

    results = query_builder.to_list()
    results.sort(key=lambda result: result["_distance"])
    return [(result["book_name"], result["_distance"]) for result in results[:top]]


def find_similar_books(book_name: str, *, top: int = 5) -> list[dict]:
    """指定書籍に意味的に近い書籍を返す。"""
    with with_db() as conn:
        ready_names = get_rag_ready_book_names(conn)
    if book_name not in ready_names:
        return []
    table = get_summaries_table()
    if table.count_rows() == 0:
        return []

    safe_name = book_name.replace("'", "''")
    matched = table.search().where(f"book_name = '{safe_name}'").to_list()
    if not matched:
        return []

    quoted = ", ".join("'" + name.replace("'", "''") + "'" for name in ready_names)
    results = (
        table.search(matched[0]["embedding"])
        .where(
            f"book_name IN ({quoted})",
            prefilter=True,
        )
        .limit(top + 1)
        .to_list()
    )
    results.sort(key=lambda result: result["_distance"])
    return [
        {
            "name": result["book_name"],
            "score": round(max(0.0, 1.0 - result["_distance"] / 2.0), 4),
        }
        for result in results
        if result["book_name"] != book_name
    ][:top]
