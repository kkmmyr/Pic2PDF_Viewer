"""LanceDB KNN ベクトル検索ロジック。

search.py に含まれていたベクトル検索固有のロジックを抽出。
"""
from __future__ import annotations

import sqlite3

from ._search_types import Scope, _resolve_book_names
from .embedder import embed_batch
from .lance_store import get_chunks_table, get_summaries_table


def vec_search(
    conn: sqlite3.Connection,
    query: str,
    scope: Scope,
    top: int = 30,
    *,
    min_chars: int = 0,
    body_page_margin: int = 0,
) -> list[tuple]:
    """[(book_name, page_no, chunk_text, distance), ...]

    Args:
        min_chars: char_count フィルタ。
        body_page_margin: 各書籍の先頭・末尾 N ページを除外。
    """
    book_names = _resolve_book_names(scope)
    if book_names is not None and not book_names:
        return []

    emb = embed_batch([query])[0]

    has_extra_filter = (
        min_chars > 0 or body_page_margin > 0 or book_names is not None
    )
    k = max(top * 5, 50) if has_extra_filter else top

    table = get_chunks_table()
    query_builder = table.search(emb).limit(k).select(
        ["chunk_id", "book_name", "page_no", "text", "char_count", "page_count"]
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
            r for r in results
            if r["page_no"] > body_page_margin
            and r["page_no"] <= (r["page_count"] - body_page_margin)
        ]

    results.sort(key=lambda r: r["_distance"])
    rows: list[tuple] = [
        (r["book_name"], r["page_no"], r["text"], r["_distance"])
        for r in results[:top]
    ]
    return rows


def search_book_summaries(
    conn: sqlite3.Connection,
    query: str,
    scope: Scope,
    *,
    top: int = 11,
) -> list[tuple[str, float]]:
    """書籍サマリの embedding に対してベクトル検索を行い、関連書籍を返す。

    Returns: [(book_name, distance), ...]（distance 昇順）
    """
    book_names = _resolve_book_names(scope)
    if book_names is not None and not book_names:
        return []

    emb = embed_batch([query])[0]

    table = get_summaries_table()
    if table.count_rows() == 0:
        return []

    k = max(top * 2, 22) if book_names is not None else top
    query_builder = table.search(emb).limit(k).select(["book_name"])
    if book_names is not None:
        quoted = ", ".join(f"'{n}'" for n in book_names)
        query_builder = query_builder.where(f"book_name IN ({quoted})", prefilter=True)

    results = query_builder.to_list()
    results.sort(key=lambda r: r["_distance"])
    return [(r["book_name"], r["_distance"]) for r in results[:top]]


def find_similar_books(book_name: str, *, top: int = 5) -> list[dict]:
    """指定書籍に意味的に近い書籍を返す（サマリ embedding の KNN、自身は除外）。

    Returns:
        [{"name": book_name, "score": float}, ...] score = コサイン類似度近似 (0〜1)
    """
    table = get_summaries_table()
    if table.count_rows() == 0:
        return []

    # 対象書籍の embedding を取得（SQL インジェクション対策でシングルクォートをエスケープ）
    safe_name = book_name.replace("'", "''")
    matched = table.search().where(f"book_name = '{safe_name}'").to_list()
    if not matched:
        return []

    emb = matched[0]["embedding"]

    # 自身を除くために top+1 件取得
    results = table.search(emb).limit(top + 1).to_list()
    results.sort(key=lambda r: r["_distance"])

    # BGE-M3 は正規化 embedding なので L2 距離 ≈ 2*(1-cosine)
    return [
        {"name": r["book_name"], "score": round(max(0.0, 1.0 - r["_distance"] / 2.0), 4)}
        for r in results
        if r["book_name"] != book_name
    ][:top]
