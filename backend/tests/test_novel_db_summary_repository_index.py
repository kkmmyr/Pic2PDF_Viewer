"""Summary repository and vector index tests."""

from unittest.mock import patch

import pytest

from services.novel_db import with_db
from services.novel_db.lance_store import get_summaries_table
from services.novel_db.migrations import upgrade_head
from services.novel_db.summarizer import (
    index_book_summary,
    load_summaries_for_books,
    update_book_summary,
)


@pytest.fixture
def db_with_book(tmp_data_dir):
    upgrade_head()
    with with_db() as conn:
        cur = conn.execute(
            "INSERT INTO books (name, pdf_path, images_dir, page_count, indexed_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("test-book", "/x.pdf", "/imgs", 10),
        )
        book_id = cur.lastrowid
        for page_no in range(1, 11):
            text = "本文" * (200 if 3 <= page_no <= 8 else 50)
            conn.execute(
                "INSERT INTO pages (book_id, page_no, image_path, full_text, char_count) VALUES (?, ?, ?, ?, ?)",
                (book_id, page_no, None, text, len(text)),
            )
        conn.commit()
    return book_id


def test_update_and_load_summary_roundtrip(db_with_book):
    with with_db() as conn:
        update_book_summary(conn, "test-book", "これはテスト要約")
        loaded = load_summaries_for_books(conn, ["test-book"])

    assert loaded == {"test-book": "これはテスト要約"}


def test_load_summaries_skips_null_and_empty(tmp_data_dir):
    """summary が NULL / 空文字の書籍は load 結果に含まれない。"""
    upgrade_head()
    with with_db() as conn:
        for name, summary in [("a", "ok"), ("b", None), ("c", "")]:
            cur = conn.execute(
                "INSERT INTO books (name, pdf_path, images_dir, page_count, indexed_at) "
                "VALUES (?, ?, ?, ?, datetime('now'))",
                (name, f"/{name}.pdf", "/imgs", 10),
            )
            if summary is not None:
                conn.execute(
                    "UPDATE books SET summary = ? WHERE id = ?",
                    (summary, cur.lastrowid),
                )
        conn.commit()

        loaded = load_summaries_for_books(conn, ["a", "b", "c"])

    assert loaded == {"a": "ok"}


def test_load_summaries_for_empty_input_returns_empty():
    # DB 接続不要（早期 return する）
    assert load_summaries_for_books(None, []) == {}  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# B-8: 書籍サマリ embedding と検索インデックス
# ---------------------------------------------------------------------------


def test_update_book_summary_indexes_vector(db_with_book):
    """update_book_summary が summary を保存し、LanceDB summaries にも upsert する。"""
    with patch("services.novel_db.summary_index.embed_batch") as mock_embed:
        # bge-m3 は 1024 次元
        mock_embed.return_value = [[0.1] * 1024]
        with with_db() as conn:
            update_book_summary(conn, "test-book", "テストサマリ")
            # books.summary 更新
            row = conn.execute(
                "SELECT summary FROM books WHERE name = ?",
                ("test-book",),
            ).fetchone()
            assert row[0] == "テストサマリ"
        # LanceDB summaries に 1 件
        table = get_summaries_table()
        n = table.count_rows()
        assert n == 1
    mock_embed.assert_called_once_with(["テストサマリ"])


def test_update_book_summary_handles_embed_failure(db_with_book):
    """embedder 失敗時はサマリ本文だけ保存し、vec 側は空のまま続行する。"""
    with patch("services.novel_db.summary_index.embed_batch") as mock_embed:
        mock_embed.side_effect = TimeoutError("ollama timeout")
        with with_db() as conn:
            update_book_summary(conn, "test-book", "テスト")
            # 本文は保存されている
            row = conn.execute(
                "SELECT summary FROM books WHERE name = ?",
                ("test-book",),
            ).fetchone()
            assert row[0] == "テスト"
        # LanceDB summaries は空のまま
        table = get_summaries_table()
        assert table.count_rows() == 0


def test_index_book_summary_can_make_embed_failure_blocking(db_with_book):
    with (
        patch(
            "services.novel_db.summary_index.embed_batch",
            side_effect=TimeoutError("ollama timeout"),
        ),
        with_db() as conn,
        pytest.raises(TimeoutError, match="ollama timeout"),
    ):
        index_book_summary(conn, 1, "テスト", raise_on_error=True)


def test_update_book_summary_replaces_existing_vector(db_with_book):
    """同 book_id への 2 回目の update は vec を置き換える（重複 INSERT しない）。"""
    with patch("services.novel_db.summary_index.embed_batch") as mock_embed:
        mock_embed.return_value = [[0.1] * 1024]
        with with_db() as conn:
            update_book_summary(conn, "test-book", "v1")
            update_book_summary(conn, "test-book", "v2")
        # LanceDB summaries に 1 件のみ（重複なし）
        table = get_summaries_table()
        assert table.count_rows() == 1


def test_update_book_summary_raises_for_missing_book(tmp_data_dir):
    upgrade_head()
    with with_db() as conn:
        with pytest.raises(ValueError, match="book not found"):
            update_book_summary(conn, "no-such-book", "サマリ")
