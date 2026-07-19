"""novel_db ライブラリ系エンドポイント（書籍一覧 / シリーズ / 著者 / 詳細）。"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from routers._deps import log_and_raise_500
from routers.api_schemas import BookDetailOut, BookSummaryOut, SeriesSummaryOut, SimilarBookOut
from services.novel_db import with_db
from services.novel_db.book_summary_search import find_similar_books
from services.novel_db.library import get_book_detail, list_authors, list_books, list_series

router = APIRouter()


@router.get("/books", response_model=list[BookSummaryOut])
@log_and_raise_500("novel_db/books")
def get_books() -> list[dict]:
    """書籍一覧 + DB 状態を返す（[API §7.1]）。"""
    with with_db() as conn:
        return [asdict(b) for b in list_books(conn)]


@router.get("/series", response_model=list[SeriesSummaryOut])
@log_and_raise_500("novel_db/series")
def get_series() -> list[dict]:
    """novel ソースのシリーズ一覧（書籍 1 件以上のみ）（[API §7.2]）。"""
    with with_db() as conn:
        return [asdict(s) for s in list_series(conn)]


@router.get("/authors", response_model=list[str])
@log_and_raise_500("novel_db/authors")
def get_authors() -> list[str]:
    """novel ソースの全書籍から作者一覧（重複なし・アルファベット順）を返す（B-21）。"""
    with with_db() as conn:
        return list_authors(conn)


@router.get("/books/{book_name}/similar", response_model=list[SimilarBookOut])
@log_and_raise_500("novel_db/books/similar")
def get_similar_books(book_name: str, top: int = 5) -> list[dict]:
    """指定書籍に意味的に近い書籍を返す（B-19）。サマリ embedding の KNN。"""
    return find_similar_books(book_name, top=min(top, 20))


@router.get("/books/{book_name:path}", response_model=BookDetailOut)
@log_and_raise_500("novel_db/books/detail")
def get_book_detail_route(book_name: str) -> dict:
    """単一書籍の詳細情報（summary / character_count / discussion_count 含む）を返す。"""
    with with_db() as conn:
        detail = get_book_detail(conn, book_name)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"book not found: {book_name}")
    return asdict(detail)
