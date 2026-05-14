"""services/novel_db/library.py の単体テスト。"""
from pathlib import Path

import pytest

from services.meta_store import save_meta
from services.novel_db import init_schema, with_db
from services.novel_db.library import list_books, list_series


@pytest.fixture
def setup_db(tmp_data_dir):
    """novel.db のスキーマを初期化する。"""
    with with_db() as conn:
        init_schema(conn)
    return tmp_data_dir


def _put_image_dir(tmp_data_dir, name: str) -> None:
    """tmp_data_dir に書籍画像ディレクトリを作る（images/{name}/）。"""
    images_dir = Path(tmp_data_dir["KINDLE_NOVEL_IMAGES_DIR"])
    (images_dir / name).mkdir(parents=True, exist_ok=True)


def _put_meta(meta_data: dict) -> None:
    """novel ソースのメタデータを DB に書き込む。"""
    save_meta("novel", meta_data)


def _insert_indexed_book(conn, name: str, page_count: int = 100) -> int:
    """books テーブルに 1 件 INSERT する。"""
    cur = conn.execute(
        "INSERT INTO books (name, pdf_path, images_dir, page_count, indexed_at) "
        "VALUES (?, ?, ?, ?, datetime('now'))",
        (name, f"/dummy/{name}.pdf", f"/dummy/images/{name}", page_count),
    )
    return cur.lastrowid


def test_list_books_returns_images_dirs_with_unindexed_status(setup_db):
    _put_image_dir(setup_db, "book-1")
    _put_image_dir(setup_db, "book-2")

    with with_db() as conn:
        books = list_books(conn)

    names = [b.name for b in books]
    assert names == ["book-1", "book-2"]
    assert all(b.is_indexed is False for b in books)
    assert all(b.page_count is None for b in books)
    assert all(b.indexed_at is None for b in books)


def test_list_books_merges_indexed_status(setup_db):
    _put_image_dir(setup_db, "book-1")
    _put_image_dir(setup_db, "book-2")

    with with_db() as conn:
        _insert_indexed_book(conn, "book-1", page_count=120)
        conn.commit()
        books = list_books(conn)

    by_name = {b.name: b for b in books}
    assert by_name["book-1"].is_indexed is True
    assert by_name["book-1"].page_count == 120
    assert by_name["book-1"].indexed_at is not None
    assert by_name["book-2"].is_indexed is False


def test_list_books_merges_meta_authors_and_series(setup_db):
    _put_image_dir(setup_db, "book-1")
    _put_meta({
        "book-1.pdf": {
            "authors": ["田中啓子"],
            "series_id": "oko-kishi",
            "series_title": "おこぼれ姫",
        }
    })

    with with_db() as conn:
        books = list_books(conn)

    assert len(books) == 1
    assert books[0].authors == ["田中啓子"]
    assert books[0].series_id == "oko-kishi"
    assert books[0].series_title == "おこぼれ姫"


def test_list_books_thumbnail_url_uses_first_image(setup_db):
    _put_image_dir(setup_db, "book-1")

    with with_db() as conn:
        books = list_books(conn)

    assert books[0].thumbnail_url == "/kindle_novel/images/book-1/001.png"


def test_list_books_url_encodes_japanese_book_name(setup_db):
    _put_image_dir(setup_db, "おこぼれ姫 1")

    with with_db() as conn:
        books = list_books(conn)

    assert "%" in books[0].thumbnail_url
    assert books[0].thumbnail_url.endswith("/001.png")


def test_list_series_excludes_unaffiliated_books(setup_db):
    _put_image_dir(setup_db, "book-1")
    _put_image_dir(setup_db, "book-2")
    _put_image_dir(setup_db, "book-orphan")
    _put_meta({
        "book-1.pdf": {
            "series_id": "oko-kishi",
            "series_title": "おこぼれ姫",
        },
        "book-2.pdf": {
            "series_id": "oko-kishi",
            "series_title": "おこぼれ姫",
        },
        # book-orphan は series_id なし
    })

    with with_db() as conn:
        series = list_series(conn)

    assert len(series) == 1
    assert series[0].id == "oko-kishi"
    assert series[0].name == "おこぼれ姫"
    assert series[0].book_count == 2


def test_list_series_empty_when_no_series_assigned(setup_db):
    _put_image_dir(setup_db, "book-1")

    with with_db() as conn:
        series = list_series(conn)

    assert series == []


def test_list_books_empty_when_no_images_dir(setup_db):
    with with_db() as conn:
        books = list_books(conn)
    assert books == []
