"""FTS5 BM25 全文検索ロジック。

search.py に含まれていた FTS5 固有のロジックを抽出。
"""
from __future__ import annotations

import html
import re
import sqlite3

from ._search_types import Scope, _resolve_book_names

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
