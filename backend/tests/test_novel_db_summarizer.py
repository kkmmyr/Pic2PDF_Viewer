"""services/novel_db/summarizer.py の単体テスト。

Qwen 呼び出し（`ask`）はモックする。本テストは:
- _chunk_for_map: チャンク分割ロジックの境界
- _load_body_text: フィルタ（min_chars / body_page_margin）の挙動
- summarize_book: map / reduce 切替と LLM 呼び出し回数
- update_book_summary / load_summaries_for_books: DB 入出力
を確認する。
"""
from unittest.mock import patch

import pytest

from services.novel_db import init_schema, with_db
from services.novel_db.lance_store import get_summaries_table
from services.novel_db.summarizer import (
    _chunk_for_map,
    _load_body_text,
    load_summaries_for_books,
    summarize_book,
    update_book_summary,
)

# ---------------------------------------------------------------------------
# _chunk_for_map
# ---------------------------------------------------------------------------

def test_chunk_short_text_returns_single_chunk():
    text = "short body"
    assert _chunk_for_map(text) == [text]


def test_chunk_long_text_splits_into_multiple():
    # 100,000 字（最大書籍と同等）
    text = ("a" * 1000 + "\n") * 100
    chunks = _chunk_for_map(text)
    assert len(chunks) >= 2
    assert len(chunks) <= 8  # _MAP_MAX_CHUNKS の上限
    # 結合すれば元のテキストに（ほぼ）戻る（行末改行差は除く）
    rejoined = "\n".join(chunks)
    assert rejoined.replace("\n", "") == text.replace("\n", "")


def test_chunk_respects_max_chunks_for_huge_text():
    # 200,000 字超でも最大 8 チャンク以内に収まる
    text = ("x" * 2000 + "\n") * 100
    chunks = _chunk_for_map(text)
    assert len(chunks) <= 8


# ---------------------------------------------------------------------------
# _load_body_text
# ---------------------------------------------------------------------------

@pytest.fixture
def db_with_book(tmp_data_dir):
    """1 冊（10 ページ）の最小データを入れた novel.db を返す。"""
    with with_db() as conn:
        init_schema(conn)
        cur = conn.execute(
            "INSERT INTO books (name, pdf_path, images_dir, page_count, indexed_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("test-book", "/x.pdf", "/imgs", 10),
        )
        book_id = cur.lastrowid
        for page_no in range(1, 11):
            text = "本文" * (200 if 3 <= page_no <= 8 else 50)
            conn.execute(
                "INSERT INTO pages (book_id, page_no, image_path, full_text, char_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (book_id, page_no, None, text, len(text)),
            )
        conn.commit()
    return book_id


def test_load_body_text_filters_margin_and_min_chars(db_with_book):
    with with_db() as conn:
        text = _load_body_text(
            conn, db_with_book, page_count=10,
            min_chars=300, body_page_margin=2,
        )
    # body_page_margin=2 → page_no 3〜8 を採用
    # min_chars=300 → 「本文」(2 字) × 200 = 400 字なので採用
    # margin の 2 ページ分（page_no 1, 2, 9, 10）は除外
    assert text.count("本文") == 200 * 6  # 3..8 の 6 ページ × 200 文字


def test_load_body_text_returns_empty_when_all_filtered(db_with_book):
    with with_db() as conn:
        text = _load_body_text(
            conn, db_with_book, page_count=10,
            min_chars=10000, body_page_margin=0,
        )
    assert text == ""


# ---------------------------------------------------------------------------
# summarize_book / update / load
# ---------------------------------------------------------------------------

def test_summarize_book_one_shot_for_short_book(db_with_book):
    """単一チャンクで収まる本では _BACKEND.ask() が 1 回だけ呼ばれる。"""
    with patch("services.novel_db._llm_backend.QWEN_BACKEND.ask") as mock_ask:
        mock_ask.return_value = "  これは要約です。  "
        with with_db() as conn:
            summary = summarize_book(
                conn, "test-book",
                min_chars=100, body_page_margin=2,
            )
    assert summary == "これは要約です。"
    assert mock_ask.call_count == 1


def test_summarize_book_map_reduce_for_long_book(tmp_data_dir):
    """長い本では map（チャンク数）+ reduce（1 回）が呼ばれる。"""
    with with_db() as conn:
        init_schema(conn)
        cur = conn.execute(
            "INSERT INTO books (name, pdf_path, images_dir, page_count, indexed_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("big-book", "/x.pdf", "/imgs", 60),
        )
        book_id = cur.lastrowid
        # 各ページ 5000 字 × 60 ページ = 300,000 字（map_max_chunks 上限近く）
        for page_no in range(1, 61):
            text = "あ" * 5000
            conn.execute(
                "INSERT INTO pages (book_id, page_no, image_path, full_text, char_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (book_id, page_no, None, text, len(text)),
            )
        conn.commit()

    with patch("services.novel_db._llm_backend.QWEN_BACKEND.ask") as mock_ask:
        mock_ask.side_effect = [f"map-{i}" for i in range(8)] + ["最終要約"]
        with with_db() as conn:
            summary = summarize_book(
                conn, "big-book",
                min_chars=100, body_page_margin=5,
            )
    assert summary == "最終要約"
    # map（最大 8 チャンク）+ reduce（1 回）
    assert mock_ask.call_count >= 2  # 少なくとも map 1 + reduce 1


def test_summarize_book_raises_for_missing_book(tmp_data_dir):
    with with_db() as conn:
        init_schema(conn)
        with pytest.raises(ValueError, match="book not found"):
            summarize_book(conn, "no-such-book")


def test_summarize_book_raises_for_empty_body(tmp_data_dir):
    with with_db() as conn:
        init_schema(conn)
        cur = conn.execute(
            "INSERT INTO books (name, pdf_path, images_dir, page_count, indexed_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("empty-book", "/x.pdf", "/imgs", 5),
        )
        book_id = cur.lastrowid
        for page_no in range(1, 6):
            conn.execute(
                "INSERT INTO pages (book_id, page_no, image_path, full_text, char_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (book_id, page_no, None, "", 0),
            )
        conn.commit()

        with pytest.raises(ValueError, match="no body content"):
            summarize_book(conn, "empty-book")


def test_update_and_load_summary_roundtrip(db_with_book):
    with with_db() as conn:
        update_book_summary(conn, "test-book", "これはテスト要約")
        loaded = load_summaries_for_books(conn, ["test-book"])

    assert loaded == {"test-book": "これはテスト要約"}


def test_load_summaries_skips_null_and_empty(tmp_data_dir):
    """summary が NULL / 空文字の書籍は load 結果に含まれない。"""
    with with_db() as conn:
        init_schema(conn)
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
    with patch("services.novel_db.summarizer.embed_batch") as mock_embed:
        # bge-m3 は 1024 次元
        mock_embed.return_value = [[0.1] * 1024]
        with with_db() as conn:
            update_book_summary(conn, "test-book", "テストサマリ")
            # books.summary 更新
            row = conn.execute(
                "SELECT summary FROM books WHERE name = ?", ("test-book",),
            ).fetchone()
            assert row[0] == "テストサマリ"
        # LanceDB summaries に 1 件
        table = get_summaries_table()
        n = table.count_rows()
        assert n == 1
    mock_embed.assert_called_once_with(["テストサマリ"])


def test_update_book_summary_handles_embed_failure(db_with_book):
    """embedder 失敗時はサマリ本文だけ保存し、vec 側は空のまま続行する。"""
    with patch("services.novel_db.summarizer.embed_batch") as mock_embed:
        mock_embed.side_effect = TimeoutError("ollama timeout")
        with with_db() as conn:
            update_book_summary(conn, "test-book", "テスト")
            # 本文は保存されている
            row = conn.execute(
                "SELECT summary FROM books WHERE name = ?", ("test-book",),
            ).fetchone()
            assert row[0] == "テスト"
        # LanceDB summaries は空のまま
        table = get_summaries_table()
        assert table.count_rows() == 0


def test_update_book_summary_replaces_existing_vector(db_with_book):
    """同 book_id への 2 回目の update は vec を置き換える（重複 INSERT しない）。"""
    with patch("services.novel_db.summarizer.embed_batch") as mock_embed:
        mock_embed.return_value = [[0.1] * 1024]
        with with_db() as conn:
            update_book_summary(conn, "test-book", "v1")
            update_book_summary(conn, "test-book", "v2")
        # LanceDB summaries に 1 件のみ（重複なし）
        table = get_summaries_table()
        assert table.count_rows() == 1


def test_update_book_summary_raises_for_missing_book(tmp_data_dir):
    with with_db() as conn:
        init_schema(conn)
        with pytest.raises(ValueError, match="book not found"):
            update_book_summary(conn, "no-such-book", "サマリ")
