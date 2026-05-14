"""Reciprocal Rank Fusion (RRF) によるハイブリッド検索オーケストレーション。

search.py に含まれていた RRF ランキングと全ページ読み込みロジックを抽出。
"""
from __future__ import annotations

import html
import sqlite3

from ._search_types import Scope, SearchHit, _fetch_main_characters, _image_url
from .fts5_search import fts_search, sanitize_snippet
from .vector_search import vec_search


def hybrid_search(
    conn: sqlite3.Connection,
    query: str,
    scope: Scope,
    *,
    top: int = 20,
    fts_n: int = 30,
    vec_n: int = 30,
    k_rrf: int = 60,
    min_chars: int = 0,
    max_per_book: int | None = None,
    body_page_margin: int = 0,
) -> list[SearchHit]:
    """FTS5 + ベクトル検索を Reciprocal Rank Fusion でページ単位に融合する。

    Args:
        min_chars: 該当 char_count 未満のページを除外（ノイズ抑制）。0 で無効。
        max_per_book: 1 書籍あたりの取得上限（書籍偏り抑制、scope=all/series 向け）。
        body_page_margin: 各書籍の先頭・末尾 N ページを除外。
    """
    fts = fts_search(
        conn, query, scope, fts_n,
        min_chars=min_chars, body_page_margin=body_page_margin,
    )
    vec = vec_search(
        conn, query, scope, vec_n,
        min_chars=min_chars, body_page_margin=body_page_margin,
    )

    pages: dict[tuple[str, int], dict] = {}

    for rank, row in enumerate(fts):
        book_name, page_no, raw_snippet, _score = row
        key = (book_name, page_no)
        entry = pages.setdefault(
            key,
            {"score": 0.0, "snippet": None, "has_highlight": False, "vec_text": None},
        )
        entry["score"] += 1.0 / (k_rrf + rank + 1)
        if entry["snippet"] is None:
            entry["snippet"] = sanitize_snippet(raw_snippet)
            entry["has_highlight"] = "<mark>" in entry["snippet"]

    for rank, row in enumerate(vec):
        book_name, page_no, chunk_text, _dist = row
        key = (book_name, page_no)
        entry = pages.setdefault(
            key,
            {"score": 0.0, "snippet": None, "has_highlight": False, "vec_text": None},
        )
        entry["score"] += 1.0 / (k_rrf + rank + 1)
        if entry["vec_text"] is None:
            entry["vec_text"] = chunk_text

    ranked = sorted(pages.items(), key=lambda x: -x[1]["score"])

    if max_per_book is not None and max_per_book > 0:
        per_book: dict[str, int] = {}
        filtered: list[tuple[tuple[str, int], dict]] = []
        for (book_name, page_no), data in ranked:
            if per_book.get(book_name, 0) >= max_per_book:
                continue
            per_book[book_name] = per_book.get(book_name, 0) + 1
            filtered.append(((book_name, page_no), data))
            if len(filtered) >= top:
                break
        ranked = filtered
    else:
        ranked = ranked[:top]

    keys = [(b, p) for (b, p), _ in ranked]
    main_chars_map = _fetch_main_characters(conn, keys)

    hits: list[SearchHit] = []
    for (book_name, page_no), data in ranked:
        if data["snippet"]:
            snippet = data["snippet"]
            has_highlight = data["has_highlight"]
        else:
            text = (data["vec_text"] or "")[:200]
            snippet = html.escape(text)
            has_highlight = False
        hits.append(
            SearchHit(
                book_name=book_name,
                page_no=page_no,
                snippet=snippet,
                has_highlight=has_highlight,
                image_url=_image_url(book_name, page_no),
                rrf_score=data["score"],
                main_characters=main_chars_map.get((book_name, page_no), []),
            )
        )
    return hits


def load_all_pages_of_book(
    conn: sqlite3.Connection,
    book_name: str,
    *,
    min_chars: int = 0,
    body_page_margin: int = 0,
) -> list[SearchHit]:
    """指定書籍の全 page を page_no 順で SearchHit リストとして返す（B-13 段階 C）。

    hybrid_search を bypass する経路。scope=book + 全 page 読み込みモード用。
    """
    book_row = conn.execute(
        "SELECT id FROM books WHERE name = ?", (book_name,),
    ).fetchone()
    if book_row is None:
        return []
    book_id = book_row[0]

    where_clauses = ["book_id = ?"]
    params: list[object] = [book_id]
    if min_chars > 0:
        where_clauses.append("char_count >= ?")
        params.append(min_chars)

    sql = (
        f"SELECT page_no, full_text "
        f"FROM pages WHERE {' AND '.join(where_clauses)} "
        f"ORDER BY page_no ASC"
    )
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        return []

    if body_page_margin > 0 and len(rows) > body_page_margin * 2:
        page_nos = [r[0] for r in rows]
        lo = page_nos[body_page_margin]
        hi = page_nos[-(body_page_margin + 1)]
        rows = [r for r in rows if lo <= r[0] <= hi]

    keys = [(book_name, r[0]) for r in rows]
    main_chars_map = _fetch_main_characters(conn, keys)

    hits: list[SearchHit] = []
    for page_no, full_text in rows:
        hits.append(
            SearchHit(
                book_name=book_name,
                page_no=page_no,
                snippet=full_text or "",
                has_highlight=False,
                image_url=_image_url(book_name, page_no),
                rrf_score=0.0,
                main_characters=main_chars_map.get((book_name, page_no), []),
            ),
        )
    return hits
