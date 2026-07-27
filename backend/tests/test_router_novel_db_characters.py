"""routers/novel_db.py のキャラクター API（B-15）テスト。"""

import pytest

from services.novel_db import with_db
from services.novel_db.character_db import CharacterStat, upsert_character
from services.novel_db.migrations import upgrade_head


@pytest.fixture
def book_with_pages(tmp_data_dir):
    """1 冊 + 数ページ（main_characters 入り）を入れた DB を返す。"""
    upgrade_head()
    with with_db() as conn:
        cur = conn.execute(
            "INSERT INTO books (name, pdf_path, images_dir, page_count, indexed_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("sample-book", "/x.pdf", "/imgs", 10),
        )
        book_id = cur.lastrowid
        page_data = [
            (1, "head", 100, None),
            (2, "レティ登場", 300, "レティ"),
            (3, "対話", 500, "レティ, デューク"),
            (4, "対話", 200, "デューク"),
        ]
        for pn, ft, cc, mc in page_data:
            conn.execute(
                "INSERT INTO pages "
                "(book_id, page_no, image_path, full_text, char_count, main_characters) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (book_id, pn, None, ft, cc, mc),
            )
        conn.commit()
    return book_id


@pytest.fixture
def db_initialized(tmp_data_dir):
    """空の novel.db を Alembic マイグレーション済みで返す。"""
    upgrade_head()
    return tmp_data_dir


def test_get_characters_returns_404_for_missing_book(client, db_initialized):
    res = client.get("/api/novel_db/books/no-such-book/characters")
    assert res.status_code == 404
    assert "book not found" in res.json()["detail"]


def test_get_characters_rejects_unsafe_book_name(client, db_initialized):
    res = client.get("/api/novel_db/books/folder/book/characters")
    assert res.status_code == 400
    assert res.json()["detail"] == "Invalid book_name"


def test_get_characters_returns_empty_list_when_none_registered(client, book_with_pages):
    """book_characters テーブルが空でも 200 + [] を返す（CLI 未実行のケース）。"""
    res = client.get("/api/novel_db/books/sample-book/characters")
    assert res.status_code == 200
    assert res.json() == []


def test_get_characters_returns_registered_characters_sorted(client, book_with_pages):
    book_id = book_with_pages
    with with_db() as conn:
        upsert_character(
            conn,
            book_id,
            CharacterStat("レティ", first_page=2, page_count=2),
            summary="レティの人物像",
        )
        upsert_character(
            conn,
            book_id,
            CharacterStat("デューク", first_page=3, page_count=2),
            summary=None,
        )

    res = client.get("/api/novel_db/books/sample-book/characters")
    assert res.status_code == 200
    body = res.json()
    # page_count 同点なら first_page 昇順 → レティ(2) → デューク(3)
    assert [c["name"] for c in body] == ["レティ", "デューク"]
    assert body[0]["has_summary"] is True
    assert body[1]["has_summary"] is False


def test_get_character_detail_returns_404_for_missing_character(client, book_with_pages):
    res = client.get("/api/novel_db/books/sample-book/characters/未登録キャラ")
    assert res.status_code == 404


def test_get_character_detail_returns_summary_and_top_scenes(client, book_with_pages):
    book_id = book_with_pages
    with with_db() as conn:
        upsert_character(
            conn,
            book_id,
            CharacterStat("レティ", first_page=2, page_count=2),
            summary="レティの人物像です",
        )

    res = client.get("/api/novel_db/books/sample-book/characters/レティ")
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "レティ"
    assert body["summary"] == "レティの人物像です"
    assert body["first_page"] == 2
    assert body["page_count"] == 2
    # レティの登場: p2(char=300), p3(char=500) → char_count 降順 → [p3, p2]
    assert [s["page_no"] for s in body["top_scenes"]] == [3, 2]
    assert body["top_scenes"][0]["char_count"] == 500


def test_get_character_detail_returns_404_for_missing_book(client, db_initialized):
    res = client.get("/api/novel_db/books/no-such-book/characters/レティ")
    assert res.status_code == 404
