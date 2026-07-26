"""ハイブリッド検索モジュール — FTS5 / ベクトル / RRF 統合。

詳細は docs/design/詳細設計/機能別/小説RAG_検索QA設計.md §1。
"""

from __future__ import annotations

import html
import re
import sqlite3
from dataclasses import dataclass
from urllib.parse import quote

from .book_summary_search import find_similar_books, search_book_summaries
from .embedder import embed_batch
from .lance_store import get_chunks_table
from .search_scope import Scope, ScopeType
from .search_scope import resolve_book_names as _resolve_book_names

# ──────────────────────────────────────────────
# 共有データクラス・ユーティリティ
# ──────────────────────────────────────────────


@dataclass
class SearchHit:
    book_name: str
    page_no: int
    snippet: str
    has_highlight: bool
    image_url: str | None
    rrf_score: float
    # ページの主要登場人物（character_extractor が生成、未抽出なら空リスト）
    main_characters: list[str] | None = None

    def __post_init__(self) -> None:
        if self.main_characters is None:
            self.main_characters = []


def _image_url(book_name: str, page_no: int) -> str:
    encoded = quote(book_name, safe="")
    return f"/kindle_novel/images/{encoded}/{page_no:03d}.png"


def _fetch_main_characters(conn: sqlite3.Connection, keys: list[tuple[str, int]]) -> dict[tuple[str, int], list[str]]:
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


# ──────────────────────────────────────────────
# FTS5 BM25 全文検索
# ──────────────────────────────────────────────

# FTS5 特殊文字（クエリ整形時に空白へ置換）
_FTS5_SPECIAL = re.compile(r'[?*"^():+\-]')
# トークン抽出（日本語: ひらがな・カタカナ・漢字 + 英数字）
_TOKEN_RE = re.compile(r"[ぁ-んァ-ヴー一-龯々ヶa-zA-Z0-9]+")
# snippet 内の `&lt;mark&gt;` 復元用
_MARK_ESCAPED = re.compile(r"&lt;(/?mark)&gt;")


def sanitize_snippet(text: str) -> str:
    """FTS5 snippet 出力を `<mark>` のみ許可する HTML として安全化する。

    1. `html.escape()` で全エスケープ
    2. `&lt;mark&gt;` / `&lt;/mark&gt;` のみを `<mark>` / `</mark>` に戻す
    """
    escaped = html.escape(text)
    return _MARK_ESCAPED.sub(r"<\1>", escaped)


def build_fts5_or_query(query: str, min_len: int = 2) -> str:
    """質問文から 2 文字以上のトークンを抽出し、FTS5 の OR フレーズ検索に整形する。"""
    cleaned = _FTS5_SPECIAL.sub(" ", query)
    tokens = [t for t in _TOKEN_RE.findall(cleaned) if len(t) >= min_len]
    if not tokens:
        return ""
    return " OR ".join(f'"{t}"' for t in tokens)


def fts_search(
    conn: sqlite3.Connection,
    query: str,
    scope: Scope,
    top: int = 30,
    *,
    min_chars: int = 0,
    body_page_margin: int = 0,
) -> list[tuple]:
    """[(book_name, page_no, raw_snippet, score), ...]

    Args:
        min_chars: char_count フィルタ。`min_chars` 未満のページを除外。
        body_page_margin: 各書籍の先頭・末尾 N ページを除外（表紙・あとがき等）。
    """
    or_query = build_fts5_or_query(query)
    if not or_query:
        return []
    book_names = _resolve_book_names(scope)
    if book_names is not None and not book_names:
        return []

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
    sql += " ORDER BY score LIMIT ?"
    params.append(top)

    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []


# ──────────────────────────────────────────────
# LanceDB KNN ベクトル検索
# ──────────────────────────────────────────────


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

    has_extra_filter = min_chars > 0 or body_page_margin > 0 or book_names is not None
    k = max(top * 5, 50) if has_extra_filter else top

    table = get_chunks_table()
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


# ──────────────────────────────────────────────
# Reciprocal Rank Fusion (RRF) ハイブリッド検索
# ──────────────────────────────────────────────


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
        conn,
        query,
        scope,
        fts_n,
        min_chars=min_chars,
        body_page_margin=body_page_margin,
    )
    vec = vec_search(
        conn,
        query,
        scope,
        vec_n,
        min_chars=min_chars,
        body_page_margin=body_page_margin,
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
        "SELECT id FROM books WHERE name = ?",
        (book_name,),
    ).fetchone()
    if book_row is None:
        return []
    book_id = book_row[0]

    where_clauses = ["book_id = ?", "index_eligible = 1"]
    params: list[object] = [book_id]
    if min_chars > 0:
        where_clauses.append("char_count >= ?")
        params.append(min_chars)

    sql = f"SELECT page_no, full_text FROM pages WHERE {' AND '.join(where_clauses)} ORDER BY page_no ASC"
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


__all__ = [
    "Scope",
    "ScopeType",
    "SearchHit",
    "build_fts5_or_query",
    "find_similar_books",
    "fts_search",
    "hybrid_search",
    "load_all_pages_of_book",
    "sanitize_snippet",
    "search_book_summaries",
    "vec_search",
]
