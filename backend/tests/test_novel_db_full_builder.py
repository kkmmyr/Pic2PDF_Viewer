"""services/novel_db/full_builder.py の単体テスト。

外部依存（LLM / embed_batch / LanceDB）はモック化し、スキップ条件・
コールバック呼び出し・DB 書き込みロジックのみを検証する。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.novel_db import with_db
from services.novel_db.full_builder import (
    _run_combined_step,
    _run_generate_contexts,
    build_book_contexts,
    build_book_full,
)
from services.novel_db.migrations import upgrade_head


@pytest.fixture
def db_conn(tmp_data_dir):
    upgrade_head()
    with with_db() as conn:
        yield conn


def _insert_book(conn, name: str, summary: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO books (name, pdf_path, images_dir, page_count, indexed_at, summary) "
        "VALUES (?, ?, ?, ?, datetime('now'), ?)",
        (name, f"/{name}.pdf", "/imgs", 10, summary),
    )
    conn.commit()
    return cur.lastrowid


def _insert_page(conn, book_id: int, page_no: int, text: str) -> int:
    cur = conn.execute(
        "INSERT INTO pages (book_id, page_no, image_path, full_text, char_count) VALUES (?, ?, ?, ?, ?)",
        (book_id, page_no, None, text, len(text)),
    )
    conn.commit()
    return cur.lastrowid


def _insert_chunk(conn, page_id: int, idx: int = 0, ctx_text: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO chunks (page_id, chunk_idx, text, char_count, contextual_text) VALUES (?, ?, ?, ?, ?)",
        (page_id, idx, "chunk text", 10, ctx_text),
    )
    conn.commit()
    return cur.lastrowid


class TestRunCombinedStep:
    """_run_combined_step のスキップ条件と正常フローを検証する。"""

    def test_skips_when_book_not_found(self, db_conn):
        logs = []
        _run_combined_step(db_conn, "no-such-book", redo=False, log=logs.append)
        assert any("skip" in m for m in logs)

    def test_skips_when_summary_and_chars_exist(self, db_conn):
        book_id = _insert_book(db_conn, "mybook", summary="既存サマリ")
        # book_characters に summary 付きレコードを追加
        db_conn.execute(
            "INSERT INTO book_characters (book_id, name, summary, first_page, page_count) VALUES (?, ?, ?, ?, ?)",
            (book_id, "キャラA", "説明", 1, 5),
        )
        db_conn.commit()

        logs = []
        with patch("services.novel_db.full_builder.summarize_book_with_characters") as mock_sum:
            _run_combined_step(db_conn, "mybook", redo=False, log=logs.append)
            mock_sum.assert_not_called()

        assert any("skip" in m for m in logs)

    def test_redo_true_skips_even_with_existing(self, db_conn):
        """redo=True なら既存のサマリ・キャラクタがあっても実行する。"""
        book_id = _insert_book(db_conn, "mybook2", summary="古いサマリ")
        db_conn.execute(
            "INSERT INTO book_characters (book_id, name, summary, first_page, page_count) VALUES (?, ?, ?, ?, ?)",
            (book_id, "キャラ", "説明", 1, 3),
        )
        db_conn.commit()

        logs = []
        mock_summarize = MagicMock(return_value=("新サマリ", {}))
        with (
            patch("services.novel_db.full_builder.summarize_book_with_characters", mock_summarize),
            patch("services.novel_db.full_builder.update_book_summary"),
        ):
            _run_combined_step(db_conn, "mybook2", redo=True, log=logs.append)

        mock_summarize.assert_called_once()

    def test_characters_are_inserted_to_db(self, db_conn):
        """summarize_book_with_characters が返したキャラクターが DB に INSERT される。"""
        book_id = _insert_book(db_conn, "charbook")
        _insert_page(db_conn, book_id, 1, "アリスはふしぎの国の住人")

        char_summaries = {"アリス": "主人公の少女"}
        mock_summarize = MagicMock(return_value=("本のサマリ", char_summaries))

        with (
            patch("services.novel_db.full_builder.summarize_book_with_characters", mock_summarize),
            patch("services.novel_db.full_builder.update_book_summary"),
        ):
            _run_combined_step(db_conn, "charbook", redo=False, log=lambda _: None)

        chars = db_conn.execute("SELECT name FROM book_characters WHERE book_id = ?", (book_id,)).fetchall()
        assert [r[0] for r in chars] == ["アリス"]


class TestRunGenerateContexts:
    """_run_generate_contexts のスキップ条件を検証する。"""

    def test_skips_when_book_not_found(self, db_conn):
        logs = []
        _run_generate_contexts(db_conn, "no-book", redo=False, log=logs.append)
        assert any("skip" in m for m in logs)

    def test_skips_when_summary_is_missing(self, db_conn):
        _insert_book(db_conn, "nosum", summary=None)
        logs = []
        _run_generate_contexts(db_conn, "nosum", redo=False, log=logs.append)
        assert any("skip" in m for m in logs)

    def test_skips_when_all_chunks_already_have_context(self, db_conn):
        """redo=False かつ全チャンクに contextual_text があればスキップ。"""
        book_id = _insert_book(db_conn, "done-book", summary="サマリあり")
        page_id = _insert_page(db_conn, book_id, 1, "本文")
        _insert_chunk(db_conn, page_id, ctx_text="既存コンテキスト")

        logs = []
        with patch("services.novel_db.full_builder.generate_chunk_context") as mock_ctx:
            _run_generate_contexts(db_conn, "done-book", redo=False, log=logs.append)
            mock_ctx.assert_not_called()

        assert any("skip" in m for m in logs)

    def test_processes_chunks_without_context(self, db_conn, monkeypatch):
        """contextual_text が NULL のチャンクのみ処理する。"""
        book_id = _insert_book(db_conn, "partial-book", summary="サマリ")
        page_id = _insert_page(db_conn, book_id, 1, "本文")
        _insert_chunk(db_conn, page_id, 0, ctx_text=None)
        _insert_chunk(db_conn, page_id, 1, ctx_text="既存")

        mock_ctx = MagicMock(return_value="生成コンテキスト")
        mock_embed = MagicMock(return_value=[[0.1] * 1024])
        mock_lance = MagicMock()
        mock_lance.delete = MagicMock()
        mock_lance.add = MagicMock()

        with (
            patch("services.novel_db.full_builder.generate_chunk_context", mock_ctx),
            patch("services.novel_db.full_builder.embed_batch", mock_embed),
            patch("services.novel_db.full_builder.get_chunks_table", return_value=mock_lance),
            patch("services.novel_db.full_builder.make_embedding_input", return_value="input"),
        ):
            _run_generate_contexts(db_conn, "partial-book", redo=False, log=lambda _: None)

        # context なしのチャンク 1 件だけが処理される
        assert mock_ctx.call_count == 1


class TestBuildBookFull:
    """build_book_full の高レベルフローを検証する。"""

    def test_calls_rebuild_and_combined_step(self, db_conn, monkeypatch):
        """rebuild_from_pages と _run_combined_step が順に呼ばれることを確認。"""
        mock_rebuild = MagicMock()
        mock_combined = MagicMock()

        with (
            patch("services.novel_db.full_builder.rebuild_from_pages", mock_rebuild),
            patch("services.novel_db.full_builder._run_combined_step", mock_combined),
        ):
            build_book_full("test-book")

        mock_rebuild.assert_called_once()
        mock_combined.assert_called_once()

    def test_step_callback_is_called(self, db_conn, monkeypatch):
        """step_callback に各ステップ名が渡される。"""
        steps = []
        mock_rebuild = MagicMock()
        mock_combined = MagicMock()

        with (
            patch("services.novel_db.full_builder.rebuild_from_pages", mock_rebuild),
            patch("services.novel_db.full_builder._run_combined_step", mock_combined),
        ):
            build_book_full("test-book", step_callback=steps.append)

        # start / step1 / step2 / finished の順で呼ばれる
        assert len(steps) >= 4
        assert "start" in steps[0]
        assert "finished" in steps[-1]


class TestBuildBookContexts:
    """build_book_contexts の高レベルフローを検証する。"""

    def test_calls_generate_contexts(self):
        mock_ctx = MagicMock()
        with patch("services.novel_db.full_builder._run_generate_contexts", mock_ctx):
            build_book_contexts("ctx-book")

        mock_ctx.assert_called_once()
