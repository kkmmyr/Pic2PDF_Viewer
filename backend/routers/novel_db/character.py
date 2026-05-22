"""novel_db キャラクター辞典エンドポイント（B-15）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from routers._deps import log_and_raise_500
from services.novel_db import with_db
from services.novel_db.character_db import (
    get_character,
    list_characters,
    top_scenes_for_character,
)

from .schemas import CharacterDetail, CharacterScene, CharacterSummary

router = APIRouter()


def _resolve_book_id(conn, book_name: str) -> int:
    row = conn.execute("SELECT id FROM books WHERE name = ?", (book_name,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"book not found: {book_name}")
    return row[0]


@router.get("/books/{book_name:path}/characters")
@log_and_raise_500("novel_db/books/characters")
def get_book_characters(book_name: str) -> list[CharacterSummary]:
    """書籍に登録済みのキャラ一覧を返す（B-15）。

    `book_characters` に未登録（CLI 未実行）の書籍は空配列。フロントは空配列なら
    「キャラ辞典 未生成」表示にフォールバックする。
    """
    with with_db() as conn:
        book_id = _resolve_book_id(conn, book_name)
        rows = list_characters(conn, book_id)
    return [
        CharacterSummary(
            name=r.name,
            first_page=r.first_page,
            page_count=r.page_count,
            has_summary=bool(r.summary and r.summary.strip()),
        )
        for r in rows
    ]


@router.get("/books/{book_name:path}/characters/{char_name}")
@log_and_raise_500("novel_db/books/character_detail")
def get_book_character_detail(book_name: str, char_name: str) -> CharacterDetail:
    """書籍 × キャラの詳細（サマリ + 主要シーン top 5）を返す（B-15）。"""
    with with_db() as conn:
        book_id = _resolve_book_id(conn, book_name)
        row = get_character(conn, book_id, char_name)
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"character not found in '{book_name}': {char_name}",
            )
        scenes = top_scenes_for_character(conn, book_id, char_name, limit=5)
    return CharacterDetail(
        name=row.name,
        first_page=row.first_page,
        page_count=row.page_count,
        summary=row.summary,
        generated_at=row.generated_at,
        top_scenes=[
            CharacterScene(page_no=pn, char_count=cc) for pn, cc in scenes
        ],
    )
