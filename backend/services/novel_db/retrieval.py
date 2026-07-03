"""55-3: post_qa / post_chat_session_start 共通の検索・コンテキスト構築ロジック。

両エンドポイントで重複していた retrieval 処理（hybrid_search デデュープ・
full_book_mode 分岐・書籍サマリ付与）を 1 か所にまとめる。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from config import (
    NOVEL_DB_BODY_PAGE_MARGIN,
    NOVEL_DB_MIN_BODY_CHARS,
    NOVEL_DB_QA_EXPAND_ENABLED,
    NOVEL_DB_QA_FULL_BOOK_MODE,
    NOVEL_DB_QA_FULL_BOOK_NUM_CTX,
    NOVEL_DB_QA_MAX_PER_BOOK,
    NOVEL_DB_QA_TOP_K,
    NOVEL_DB_QA_TOP_SUMMARIES,
)
from services.novel_db.llm import LLM_OPTIONS
from services.novel_db.query_expander import expand_query
from services.novel_db.search import (
    Scope,
    SearchHit,
    hybrid_search,
    load_all_pages_of_book,
    search_book_summaries,
)
from services.novel_db.summarizer import load_summaries_for_books


@dataclass
class RetrievalResult:
    hits: list[SearchHit]
    book_summaries: dict[str, str] | None
    qa_options: dict


def retrieve(conn: sqlite3.Connection, question: str, scope: Scope) -> RetrievalResult:
    """scope・question に応じた hits / book_summaries / qa_options を返す。

    full_book_mode（scope=book + NOVEL_DB_QA_FULL_BOOK_MODE 有効）のとき
    全ページ読み。それ以外は hybrid_search + Query Expansion + 書籍サマリ付与。
    """
    full_book_mode = NOVEL_DB_QA_FULL_BOOK_MODE and scope.type == "book" and scope.id is not None
    qa_options = {**LLM_OPTIONS, "num_ctx": NOVEL_DB_QA_FULL_BOOK_NUM_CTX} if full_book_mode else LLM_OPTIONS

    if full_book_mode:
        assert scope.id is not None  # full_book_mode は scope.id != None を条件に設定される
        hits = load_all_pages_of_book(
            conn,
            scope.id,
            min_chars=NOVEL_DB_MIN_BODY_CHARS,
            body_page_margin=NOVEL_DB_BODY_PAGE_MARGIN,
        )
        return RetrievalResult(hits=hits, book_summaries=None, qa_options=qa_options)

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
            min_chars=NOVEL_DB_MIN_BODY_CHARS,
            max_per_book=max_per_book,
            body_page_margin=NOVEL_DB_BODY_PAGE_MARGIN,
        )
        for h in sub_rows:
            key = (h.book_name, h.page_no)
            existing = rows_by_key.get(key)
            if existing is None or h.rrf_score > existing.rrf_score:
                rows_by_key[key] = h
    hits = sorted(rows_by_key.values(), key=lambda h: -h.rrf_score)[:NOVEL_DB_QA_TOP_K]

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
            hit_book_names | {name for name, _ in summary_hits},
        )
        book_summaries = load_summaries_for_books(conn, relevant_book_names)
    else:
        book_summaries = None

    return RetrievalResult(hits=hits, book_summaries=book_summaries, qa_options=qa_options)
