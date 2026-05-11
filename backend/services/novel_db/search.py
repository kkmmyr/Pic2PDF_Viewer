"""ハイブリッド検索（FTS5 OR + ベクトル + RRF）。

詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §6。
"""
from __future__ import annotations

import html
import re
import sqlite3
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

from services.meta_store import load_meta

from .embedder import embed_batch, serialize_f32

# FTS5 特殊文字（クエリ整形時に空白へ置換）
_FTS5_SPECIAL = re.compile(r'[?*"^():+\-]')
# トークン抽出（日本語: ひらがな・カタカナ・漢字 + 英数字）
_TOKEN_RE = re.compile(r"[ぁ-んァ-ヴー一-龯々ヶa-zA-Z0-9]+")
# snippet 内の `&lt;mark&gt;` 復元用
_MARK_ESCAPED = re.compile(r"&lt;(/?mark)&gt;")


ScopeType = Literal["all", "series", "book"]


@dataclass
class Scope:
    type: ScopeType
    id: str | None = None  # series_id or book_name (`type='all'` のとき None)


@dataclass
class SearchHit:
    book_name: str
    page_no: int
    snippet: str
    has_highlight: bool
    image_url: str | None
    rrf_score: float
    # ページの主要登場人物（character_extractor が生成、未抽出なら空リスト）
    # LLM プロンプトでキャラ帰属の誤りを抑制するために使う
    main_characters: list[str] | None = None

    def __post_init__(self) -> None:
        if self.main_characters is None:
            self.main_characters = []


# ---------------------------------------------------------------------------
# クエリ整形・サニタイゼーション
# ---------------------------------------------------------------------------

def build_fts5_or_query(query: str, min_len: int = 2) -> str:
    """質問文から 2 文字以上のトークンを抽出し、FTS5 の OR フレーズ検索に整形する。"""
    cleaned = _FTS5_SPECIAL.sub(" ", query)
    tokens = [t for t in _TOKEN_RE.findall(cleaned) if len(t) >= min_len]
    if not tokens:
        return ""
    return " OR ".join(f'"{t}"' for t in tokens)


def sanitize_snippet(text: str) -> str:
    """FTS5 snippet 出力を `<mark>` のみ許可する HTML として安全化する。

    手順:
    1. `html.escape()` で `<`, `>`, `&`, `"`, `'` を全エスケープ
    2. `&lt;mark&gt;` / `&lt;/mark&gt;` のみを `<mark>` / `</mark>` に戻す
    """
    escaped = html.escape(text)
    return _MARK_ESCAPED.sub(r"<\1>", escaped)


def _image_url(book_name: str, page_no: int) -> str:
    encoded = quote(book_name, safe="")
    return f"/kindle_novel/images/{encoded}/{page_no:03d}.png"


# ---------------------------------------------------------------------------
# scope → 書籍名フィルタ
# ---------------------------------------------------------------------------

def _resolve_book_names(scope: Scope) -> list[str] | None:
    """scope=all のとき None（全件）、それ以外は対象書籍名のリスト（空なら 0 件）。"""
    if scope.type == "all":
        return None
    if scope.type == "book":
        return [scope.id] if scope.id else []
    if scope.type == "series":
        if not scope.id:
            return []
        meta = load_meta("novel")
        names: list[str] = []
        for key, entry in meta.items():
            if entry.get("series_id") != scope.id:
                continue
            if not key.endswith(".pdf"):
                continue
            names.append(key[: -len(".pdf")])
        return names
    return []


# ---------------------------------------------------------------------------
# FTS5 検索
# ---------------------------------------------------------------------------

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
            例えば 5 なら page_no が 6 以上 (page_count - 5) 以下のページのみ対象。
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


# ---------------------------------------------------------------------------
# ベクトル検索
# ---------------------------------------------------------------------------

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
    emb_blob = serialize_f32(emb)

    # sqlite-vec の MATCH/k は必須なので、まず k 件取ってから p.char_count / page_no
    # フィルタを適用する（フィルタされる分を見越して k を多めに取得）
    has_extra_filter = (
        min_chars > 0 or body_page_margin > 0 or book_names is not None
    )
    k = max(top * 5, 50) if has_extra_filter else top

    if book_names is not None:
        placeholders = ",".join(["?"] * len(book_names))
        sql = f"""
            SELECT b.name, p.page_no, c.text, distance
            FROM chunks_vec
            JOIN chunks c ON c.id = chunks_vec.rowid
            JOIN pages p ON c.page_id = p.id
            JOIN books b ON p.book_id = b.id
            WHERE chunks_vec.embedding MATCH ?
              AND chunks_vec.k = ?
              AND b.name IN ({placeholders})
              AND p.char_count >= ?
              AND p.page_no > ?
              AND p.page_no <= b.page_count - ?
            ORDER BY distance LIMIT ?
        """
        params: list = [
            emb_blob,
            k,
            *book_names,
            min_chars,
            body_page_margin,
            body_page_margin,
            top,
        ]
    else:
        sql = """
            SELECT b.name, p.page_no, c.text, distance
            FROM chunks_vec
            JOIN chunks c ON c.id = chunks_vec.rowid
            JOIN pages p ON c.page_id = p.id
            JOIN books b ON p.book_id = b.id
            WHERE chunks_vec.embedding MATCH ?
              AND chunks_vec.k = ?
              AND p.char_count >= ?
              AND p.page_no > ?
              AND p.page_no <= b.page_count - ?
            ORDER BY distance LIMIT ?
        """
        params = [emb_blob, k, min_chars, body_page_margin, body_page_margin, top]

    return conn.execute(sql, params).fetchall()


# ---------------------------------------------------------------------------
# ハイブリッド (RRF)
# ---------------------------------------------------------------------------

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
            None で無効。
        body_page_margin: 各書籍の先頭・末尾 N ページを除外
            （表紙・人物紹介・目次・あとがき・解説・奥付の除外、ノイズ抑制）。
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

    # 書籍ごと max 件で絞る（指定があるとき）
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

    # 主要登場人物を一括取得（DB ラウンドトリップ削減）
    keys = [(b, p) for (b, p), _ in ranked]
    main_chars_map = _fetch_main_characters(conn, keys)

    hits: list[SearchHit] = []
    for (book_name, page_no), data in ranked:
        if data["snippet"]:
            snippet = data["snippet"]
            has_highlight = data["has_highlight"]
        else:
            # FTS5 ヒットなし → ベクトルチャンク先頭 200 字を HTML エスケープのみ
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
    フィルタは hybrid_search と同じ規約に揃える（min_chars / body_page_margin で
    表紙・章扉・あとがき等を除外可能）。snippet には `pages.full_text` をそのまま
    入れる（FTS5 の `<mark>` ハイライトは無し、HTML エスケープは LLM 入力では不要）。
    """
    # 書籍メタ取得（先頭・末尾除外用に page 数を見るため books.id も同時に）
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

    # body_page_margin で先頭・末尾 N page を除外する。
    # hybrid_search 側と挙動を揃えるため、書籍内の page_no 最小・最大からの差分で判定
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
                rrf_score=0.0,  # ランキングなし（page_no 順）
                main_characters=main_chars_map.get((book_name, page_no), []),
            ),
        )
    return hits


def search_book_summaries(
    conn: sqlite3.Connection,
    query: str,
    scope: Scope,
    *,
    top: int = 11,
) -> list[tuple[str, float]]:
    """書籍サマリの embedding に対してベクトル検索を行い、関連書籍を返す。

    B-8: scope=all / scope=series での概括的な質問に対して、サマリ自体を retrieval
    候補とし、ページヒットだけでは拾えなかった書籍も俯瞰サマリとしてプロンプトに
    入れる。FTS5 はサマリにかけても抽象表現で keyword 一致しにくいため使わず、
    bge-m3 のベクトル検索のみを使う。

    Returns: [(book_name, distance), ...]（distance 昇順）
    """
    book_names = _resolve_book_names(scope)
    if book_names is not None and not book_names:
        return []

    # book_summaries_vec が無い古い DB との互換性
    has_vec = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='book_summaries_vec'",
    ).fetchone()
    if has_vec is None:
        return []

    emb = embed_batch([query])[0]
    emb_blob = serialize_f32(emb)

    # vec0 は MATCH/k 必須。scope フィルタ用に多めに取得。
    k = max(top * 2, 22) if book_names is not None else top
    if book_names is not None:
        placeholders = ",".join(["?"] * len(book_names))
        sql = f"""
            SELECT b.name, distance
            FROM book_summaries_vec
            JOIN books b ON b.id = book_summaries_vec.rowid
            WHERE book_summaries_vec.embedding MATCH ?
              AND book_summaries_vec.k = ?
              AND b.name IN ({placeholders})
            ORDER BY distance LIMIT ?
        """  # noqa: S608
        params: list = [emb_blob, k, *book_names, top]
    else:
        sql = """
            SELECT b.name, distance
            FROM book_summaries_vec
            JOIN books b ON b.id = book_summaries_vec.rowid
            WHERE book_summaries_vec.embedding MATCH ?
              AND book_summaries_vec.k = ?
            ORDER BY distance LIMIT ?
        """
        params = [emb_blob, top, top]

    return [(name, dist) for name, dist in conn.execute(sql, params)]


def _fetch_main_characters(
    conn: sqlite3.Connection, keys: list[tuple[str, int]]
) -> dict[tuple[str, int], list[str]]:
    """指定された (book_name, page_no) の組に対して main_characters を一括取得する。"""
    if not keys:
        return {}
    # main_characters 列が無い古い DB との互換性
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
