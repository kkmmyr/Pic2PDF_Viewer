"""チャンク文脈生成application serviceの契約テスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.novel_db import context_generation, full_builder, with_db
from services.novel_db.context_generation import _run_generate_contexts, build_book_contexts
from services.novel_db.migrations import upgrade_head


@pytest.fixture
def db_conn(tmp_data_dir):
    upgrade_head()
    with with_db() as conn:
        yield conn


def _insert_book(conn, name: str, summary: str | None = None) -> int:
    cursor = conn.execute(
        """
        INSERT INTO books
            (name, pdf_path, images_dir, page_count, indexed_at, summary, catalog_summary)
        VALUES (?, ?, ?, ?, datetime('now'), ?, ?)
        """,
        (name, f"/{name}.pdf", "/imgs", 10, summary, "一覧向け要約" if summary else None),
    )
    conn.commit()
    return cursor.lastrowid


def _insert_page(conn, book_id: int, page_no: int, text: str) -> int:
    cursor = conn.execute(
        "INSERT INTO pages (book_id, page_no, image_path, full_text, char_count) VALUES (?, ?, ?, ?, ?)",
        (book_id, page_no, None, text, len(text)),
    )
    conn.commit()
    return cursor.lastrowid


def _insert_chunk(conn, page_id: int, idx: int = 0, ctx_text: str | None = None) -> int:
    cursor = conn.execute(
        "INSERT INTO chunks (page_id, chunk_idx, text, char_count, contextual_text) VALUES (?, ?, ?, ?, ?)",
        (page_id, idx, "chunk text", 10, ctx_text),
    )
    conn.commit()
    return cursor.lastrowid


def test_full_builder_preserves_public_context_builder_import() -> None:
    assert full_builder.build_book_contexts is context_generation.build_book_contexts


class TestRunGenerateContexts:
    def test_skips_when_book_not_found(self, db_conn):
        logs: list[str] = []
        _run_generate_contexts(db_conn, "no-book", redo=False, log=logs.append)
        assert any("skip" in message for message in logs)

    def test_skips_when_summary_is_missing(self, db_conn):
        _insert_book(db_conn, "nosum")
        logs: list[str] = []
        _run_generate_contexts(db_conn, "nosum", redo=False, log=logs.append)
        assert any("skip" in message for message in logs)

    def test_skips_when_all_chunks_already_have_context(self, db_conn):
        book_id = _insert_book(db_conn, "done-book", summary="サマリあり")
        page_id = _insert_page(db_conn, book_id, 1, "本文")
        _insert_chunk(db_conn, page_id, ctx_text="既存コンテキスト")

        logs: list[str] = []
        with patch("services.novel_db.context_generation.generate_chunk_context") as generate:
            _run_generate_contexts(db_conn, "done-book", redo=False, log=logs.append)
            generate.assert_not_called()

        assert any("skip" in message for message in logs)

    def test_processes_only_chunks_without_context(self, db_conn):
        book_id = _insert_book(db_conn, "partial-book", summary="サマリ")
        page_id = _insert_page(db_conn, book_id, 1, "本文")
        _insert_chunk(db_conn, page_id, 0)
        _insert_chunk(db_conn, page_id, 1, ctx_text="既存")

        generate = MagicMock(return_value="生成コンテキスト")
        lance_table = MagicMock()
        with (
            patch("services.novel_db.context_generation.generate_chunk_context", generate),
            patch("services.novel_db.context_generation.embed_batch", return_value=[[0.1] * 1024]),
            patch("services.novel_db.context_generation.get_chunks_table", return_value=lance_table),
        ):
            _run_generate_contexts(db_conn, "partial-book", redo=False, log=lambda _: None)

        generate.assert_called_once()

    def test_batches_embedding_and_storage_updates(self, db_conn):
        book_id = _insert_book(db_conn, "batch-book", summary="サマリ")
        page_id = _insert_page(db_conn, book_id, 1, "本文")
        chunk_ids = [_insert_chunk(db_conn, page_id, idx) for idx in range(3)]

        lance_table = MagicMock()
        with (
            patch(
                "services.novel_db.context_generation.generate_chunk_context",
                side_effect=["文脈1", "文脈2", "文脈3"],
            ),
            patch(
                "services.novel_db.context_generation.embed_batch",
                return_value=[[0.1] * 1024, [0.2] * 1024, [0.3] * 1024],
            ) as embed,
            patch("services.novel_db.context_generation.get_chunks_table", return_value=lance_table),
        ):
            _run_generate_contexts(db_conn, "batch-book", redo=False, log=lambda _: None)

        embed.assert_called_once()
        lance_table.delete.assert_called_once()
        assert " IN (" in lance_table.delete.call_args.args[0]
        assert len(lance_table.add.call_args.args[0]) == 3
        stored = db_conn.execute(
            "SELECT contextual_text FROM chunks WHERE id IN (?, ?, ?) ORDER BY id",
            chunk_ids,
        ).fetchall()
        assert [row[0] for row in stored] == ["文脈1", "文脈2", "文脈3"]

    def test_failed_generation_remains_retryable(self, db_conn):
        book_id = _insert_book(db_conn, "generation-fail-book", summary="サマリ")
        page_id = _insert_page(db_conn, book_id, 1, "本文")
        chunk_id = _insert_chunk(db_conn, page_id)

        with (
            patch(
                "services.novel_db.context_generation.generate_chunk_context",
                side_effect=RuntimeError("generation down"),
            ),
            patch("services.novel_db.context_generation.get_chunks_table", return_value=MagicMock()),
        ):
            _run_generate_contexts(db_conn, "generation-fail-book", redo=False, log=lambda _: None)

        stored = db_conn.execute(
            "SELECT contextual_text FROM chunks WHERE id = ?",
            (chunk_id,),
        ).fetchone()
        assert stored[0] is None

    def test_failed_batch_remains_retryable(self, db_conn):
        book_id = _insert_book(db_conn, "retry-book", summary="サマリ")
        page_id = _insert_page(db_conn, book_id, 1, "本文")
        chunk_id = _insert_chunk(db_conn, page_id)

        with (
            patch("services.novel_db.context_generation.generate_chunk_context", return_value="生成文脈"),
            patch("services.novel_db.context_generation.embed_batch", side_effect=RuntimeError("down")),
            patch("services.novel_db.context_generation.get_chunks_table", return_value=MagicMock()),
        ):
            _run_generate_contexts(db_conn, "retry-book", redo=False, log=lambda _: None)

        stored = db_conn.execute(
            "SELECT contextual_text FROM chunks WHERE id = ?",
            (chunk_id,),
        ).fetchone()
        assert stored[0] is None


def test_build_book_contexts_calls_generate_contexts() -> None:
    generate = MagicMock()
    with patch("services.novel_db.context_generation._run_generate_contexts", generate):
        build_book_contexts("ctx-book")

    generate.assert_called_once()
