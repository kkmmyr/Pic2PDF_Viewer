"""ハイブリッド検索モジュール — FTS5 / ベクトル / RRF 統合。

詳細は docs/design/詳細設計/機能別/小説RAG_検索QA設計.md §1。
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import time

from config.novel_db import novel_db_settings as _cfg
from utils.logger import get_logger

from .book_summary_search import find_similar_books, search_book_summaries
from .embedder import embed_batch
from .lance_store import get_chunks_table
from .page_fts import search_page_fts
from .search_presentation import SearchHit, present_full_book_pages, present_ranked_pages, sanitize_snippet
from .search_queries import fetch_main_characters as _fetch_main_characters
from .search_queries import query_fts_rows, query_vector_rows
from .search_ranking import rank_pages
from .search_scope import Scope, ScopeType
from .search_scope import resolve_book_names as _resolve_book_names

logger = get_logger(__name__)

# ──────────────────────────────────────────────
# FTS5 BM25 全文検索
# ──────────────────────────────────────────────

# FTS5 特殊文字（クエリ整形時に空白へ置換）
_FTS5_SPECIAL = re.compile(r'[?*"^():+\-]')
# トークン抽出（日本語: ひらがな・カタカナ・漢字 + 英数字）
_TOKEN_RE = re.compile(r"[ぁ-んァ-ヴー一-龯々ヶa-zA-Z0-9]+")


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

    return query_fts_rows(
        conn,
        or_query,
        book_names,
        top,
        min_chars=min_chars,
        body_page_margin=body_page_margin,
    )


def _search_key_set(rows: list[tuple]) -> set[tuple[str, int]]:
    return {(str(row[0]), int(row[1])) for row in rows}


def lexical_search(
    conn: sqlite3.Connection,
    query: str,
    scope: Scope,
    top: int = 30,
    *,
    min_chars: int = 0,
    body_page_margin: int = 0,
) -> list[tuple]:
    """設定に応じてFTS5 / ICUを選び、shadowまたは障害時はFTS5を返す。"""
    mode = _cfg.NOVEL_DB_LEXICAL_BACKEND
    kwargs = {
        "min_chars": min_chars,
        "body_page_margin": body_page_margin,
    }
    if mode == "fts5":
        return fts_search(conn, query, scope, top, **kwargs)

    query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]
    if mode == "shadow":
        started = time.perf_counter()
        fts_rows = fts_search(conn, query, scope, top, **kwargs)
        fts_ms = (time.perf_counter() - started) * 1000.0
        started = time.perf_counter()
        try:
            icu_rows = search_page_fts(conn, query, scope, top, **kwargs)
        except Exception as exc:
            icu_ms = (time.perf_counter() - started) * 1000.0
            logger.warning(
                "lexical shadow unavailable: query_hash=%s fts_count=%d fts_ms=%.3f icu_ms=%.3f error_type=%s",
                query_hash,
                len(fts_rows),
                fts_ms,
                icu_ms,
                type(exc).__name__,
            )
            return fts_rows
        icu_ms = (time.perf_counter() - started) * 1000.0
        overlap = len(_search_key_set(fts_rows) & _search_key_set(icu_rows))
        logger.info(
            "lexical shadow: query_hash=%s fts_count=%d icu_count=%d overlap=%d fts_ms=%.3f icu_ms=%.3f",
            query_hash,
            len(fts_rows),
            len(icu_rows),
            overlap,
            fts_ms,
            icu_ms,
        )
        return fts_rows

    if mode == "lance_icu":
        try:
            return search_page_fts(conn, query, scope, top, **kwargs)
        except Exception as exc:
            logger.warning(
                "lexical ICU fallback: query_hash=%s error_type=%s",
                query_hash,
                type(exc).__name__,
            )
            return fts_search(conn, query, scope, top, **kwargs)

    raise RuntimeError(f"unsupported lexical backend: {mode}")


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

    return query_vector_rows(
        get_chunks_table(),
        emb,
        book_names,
        top,
        min_chars=min_chars,
        body_page_margin=body_page_margin,
    )


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
    fts = lexical_search(
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

    ranked = rank_pages(fts, vec, top=top, k_rrf=k_rrf, max_per_book=max_per_book)
    keys = [(page.book_name, page.page_no) for page in ranked]
    main_chars_map = _fetch_main_characters(conn, keys)
    return present_ranked_pages(ranked, main_chars_map)


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

    return present_full_book_pages(book_name, rows, main_chars_map)


__all__ = [
    "Scope",
    "ScopeType",
    "SearchHit",
    "build_fts5_or_query",
    "find_similar_books",
    "fts_search",
    "hybrid_search",
    "lexical_search",
    "load_all_pages_of_book",
    "sanitize_snippet",
    "search_book_summaries",
    "vec_search",
]
