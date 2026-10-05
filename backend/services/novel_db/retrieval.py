"""55-3: post_qa / post_chat_session_start 共通の検索・コンテキスト構築ロジック。

両エンドポイントで重複していた retrieval 処理（hybrid_search デデュープ・
full_book_mode 分岐・書籍サマリ付与）を 1 か所にまとめる。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace

from config import (
    NOVEL_DB_QA_EXPAND_ENABLED,
    NOVEL_DB_QA_FULL_BOOK_MODE,
    NOVEL_DB_QA_FULL_BOOK_NUM_CTX,
    NOVEL_DB_QA_MAX_PER_BOOK,
    NOVEL_DB_QA_TOP_K,
    NOVEL_DB_QA_TOP_SUMMARIES,
)
from services.novel_db.book_summary_search import search_book_summaries
from services.novel_db.llm import LLM_OPTIONS
from services.novel_db.query_expander import expand_query
from services.novel_db.search import (
    Scope,
    SearchHit,
    hybrid_search,
    load_all_pages_of_book,
)
from services.novel_db.summarizer import load_summaries_for_books

from .search_scope import resolve_book_names
from .summary_repository import get_rag_ready_book_names


class RagNotReady(ValueError):
    """The requested body is published but its RAG artifacts are unavailable."""


@dataclass
class RetrievalResult:
    hits: list[SearchHit]
    book_summaries: dict[str, str] | None
    qa_options: dict


def _canonical_hits(conn: sqlite3.Connection, hits: list[SearchHit]) -> list[SearchHit]:
    result = []
    for hit in hits:
        if type(hit.page_no) is not int or hit.page_no <= 0:
            raise ValueError("RAG hit has an invalid page number")
        rows = conn.execute(
            "SELECT p.full_text FROM pages p JOIN books b ON b.id=p.book_id "
            "WHERE b.name=? AND p.page_no=? AND p.index_eligible=1 AND b.indexed_at IS NOT NULL",
            (hit.book_name, hit.page_no),
        ).fetchall()
        if len(rows) != 1 or not isinstance(rows[0][0], str) or not rows[0][0].strip():
            raise ValueError(f"RAG canonical body unavailable: {hit.book_name} page {hit.page_no}")
        result.append(replace(hit, snippet=rows[0][0], has_highlight=False))
    return result


def retrieve(conn: sqlite3.Connection, question: str, scope: Scope) -> RetrievalResult:
    """scope・question に応じた hits / book_summaries / qa_options を返す。

    full_book_mode（scope=book + NOVEL_DB_QA_FULL_BOOK_MODE 有効）のとき
    全ページ読み。それ以外は hybrid_search + Query Expansion + 書籍サマリ付与。
    """
    ready_names = set(get_rag_ready_book_names(conn, resolve_book_names(scope)))
    if scope.type == "book" and scope.id not in ready_names:
        raise RagNotReady(f"RAG is not available until rebuilding: {scope.id}")
    full_book_mode = NOVEL_DB_QA_FULL_BOOK_MODE and scope.type == "book" and scope.id is not None
    qa_options = {**LLM_OPTIONS, "num_ctx": NOVEL_DB_QA_FULL_BOOK_NUM_CTX} if full_book_mode else LLM_OPTIONS

    if full_book_mode:
        assert scope.id is not None  # full_book_mode は scope.id != None を条件に設定される
        hits = load_all_pages_of_book(
            conn,
            scope.id,
            min_chars=0,
            body_page_margin=0,
        )
        return RetrievalResult(hits=hits, book_summaries=None, qa_options=qa_options)

    if not ready_names:
        return RetrievalResult(hits=[], book_summaries=None, qa_options=qa_options)

    # 通常 RAG 経路
    # scope=all / series では書籍偏り抑制のため max_per_book を有効化
    max_per_book = NOVEL_DB_QA_MAX_PER_BOOK if scope.type in ("all", "series") else None
    # B-11 Query Expansion: 展開無効 / 失敗時は元の質問のみのリストになる
    queries = expand_query(question) if NOVEL_DB_QA_EXPAND_ENABLED else [question]

    # 各クエリで hybrid_search → (book_name, page_no) でデデュープ、スコア最大値採用
    rows_by_key: dict[tuple[str, int], SearchHit] = {}
    for q in queries:
        sub_rows = hybrid_search(
            conn,
            q,
            scope,
            top=NOVEL_DB_QA_TOP_K,
            min_chars=0,
            max_per_book=max_per_book,
            body_page_margin=0,
        )
        for h in sub_rows:
            if h.book_name not in ready_names:
                continue
            key = (h.book_name, h.page_no)
            existing = rows_by_key.get(key)
            if existing is None or h.rrf_score > existing.rrf_score:
                rows_by_key[key] = h
    hits = _canonical_hits(conn, sorted(rows_by_key.values(), key=lambda h: -h.rrf_score)[:NOVEL_DB_QA_TOP_K])

    # scope=all / series ではヒット書籍の俯瞰サマリをプロンプトに付与する
    # B-8: ページヒット書籍 + サマリベクトル検索 top-K を合流させる
    if scope.type in ("all", "series"):
        hit_book_names = {h.book_name for h in hits}
        summary_hits = search_book_summaries(
            conn,
            question,
            scope,
            top=NOVEL_DB_QA_TOP_SUMMARIES,
        )
        relevant_book_names = sorted(
            hit_book_names | {name for name, _ in summary_hits if name in ready_names},
        )
        book_summaries = load_summaries_for_books(conn, relevant_book_names)
    else:
        book_summaries = None

    return RetrievalResult(hits=hits, book_summaries=book_summaries, qa_options=qa_options)
