"""書籍サマリ embedding を使う書籍単位の検索。"""

from __future__ import annotations

import sqlite3

from .embedder import embed_batch
from .lance_store import get_summaries_table
from .search_scope import Scope, resolve_book_names


def search_book_summaries(
    conn: sqlite3.Connection,
    query: str,
    scope: Scope,
    *,
    top: int = 11,
) -> list[tuple[str, float]]:
    """書籍サマリをベクトル検索し、距離の昇順で返す。"""
    book_names = resolve_book_names(scope)
    if book_names is not None and not book_names:
        return []

    table = get_summaries_table()
    if table.count_rows() == 0:
        return []

    embedding = embed_batch([query])[0]
    limit = max(top * 2, 22) if book_names is not None else top
    query_builder = table.search(embedding).limit(limit).select(["book_name"])
    if book_names is not None:
        quoted = ", ".join(f"'{name}'" for name in book_names)
        query_builder = query_builder.where(
            f"book_name IN ({quoted})",
            prefilter=True,
        )

    results = query_builder.to_list()
    results.sort(key=lambda result: result["_distance"])
    return [(result["book_name"], result["_distance"]) for result in results[:top]]


def find_similar_books(book_name: str, *, top: int = 5) -> list[dict]:
    """指定書籍に意味的に近い書籍を返す。"""
    table = get_summaries_table()
    if table.count_rows() == 0:
        return []

    safe_name = book_name.replace("'", "''")
    matched = table.search().where(f"book_name = '{safe_name}'").to_list()
    if not matched:
        return []

    results = table.search(matched[0]["embedding"]).limit(top + 1).to_list()
    results.sort(key=lambda result: result["_distance"])
    return [
        {
            "name": result["book_name"],
            "score": round(max(0.0, 1.0 - result["_distance"] / 2.0), 4),
        }
        for result in results
        if result["book_name"] != book_name
    ][:top]
