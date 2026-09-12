"""本構築の公開transaction・索引失敗・ジョブ通知を分離前後で固定する。"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from services.novel_db import context_generation, full_builder, summary_index, with_db
from services.novel_db.generated_content_snapshot import capture_generated_content
from services.novel_db.generation.full_build_content import CharacterRow, GeneratedBookContent
from services.novel_db.generation.full_build_repository import replace_published_content
from services.novel_db.migrations import upgrade_head

BOOK = "publication-contract"
GENERATED = ("新しい詳細", "新しい一覧", {"アリス": "新しい人物説明"})


def test_full_build_public_entry_keeps_shared_types_and_operations() -> None:
    assert full_builder.GeneratedBookContent is GeneratedBookContent
    assert full_builder.replace_published_content is replace_published_content
    assert full_builder.build_book_contexts is context_generation.build_book_contexts
    assert full_builder.__all__ == ["build_book_contexts", "build_book_full"]


class CommitFailureConnection(sqlite3.Connection):
    fail_commit = False

    def commit(self):
        if self.fail_commit:
            raise sqlite3.OperationalError("injected commit failure")
        super().commit()


@pytest.fixture
def published_db(tmp_data_dir):
    upgrade_head()
    with with_db() as conn:
        path = conn.execute("PRAGMA database_list").fetchone()[2]
    conn = sqlite3.connect(path, factory=CommitFailureConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """INSERT INTO books
           (name, pdf_path, images_dir, page_count, summary, summary_generated_at,
            catalog_summary, catalog_summary_generated_at)
           VALUES (?, '/book.pdf', '/images', 1, '旧詳細', '2026-01-01', '旧一覧', '2026-01-02')""",
        (BOOK,),
    )
    book_id = conn.execute("SELECT id FROM books WHERE name = ?", (BOOK,)).fetchone()[0]
    conn.execute(
        """INSERT INTO pages (book_id, page_no, full_text, char_count)
           VALUES (?, 1, 'アリスは出発した。', 9)""",
        (book_id,),
    )
    conn.execute(
        """INSERT INTO book_characters (book_id, name, summary, first_page, page_count, generated_at)
           VALUES (?, 'アリス', '旧人物説明', 1, 1, '2026-01-03')""",
        (book_id,),
    )
    conn.commit()
    try:
        yield conn
    finally:
        conn.close()


def snapshot(conn):
    return capture_generated_content(conn, BOOK, captured_at="fixed")


def test_repository_leaves_publication_uncommitted_for_caller(published_db):
    conn = published_db
    before = snapshot(conn)
    book_id = conn.execute("SELECT id FROM books WHERE name = ?", (BOOK,)).fetchone()[0]

    replace_published_content(
        conn,
        book_id,
        GeneratedBookContent(*GENERATED),
        [CharacterRow("アリス", "新しい人物説明", 1, 1)],
    )

    assert conn.in_transaction
    assert snapshot(conn).summary == GENERATED[0]
    with with_db() as observer:
        assert snapshot(observer) == before
    conn.rollback()
    assert snapshot(conn) == before


@pytest.mark.parametrize("failure", ["update", "delete", "insert", "commit"])
def test_sql_failure_rolls_back_entire_publication(published_db, monkeypatch, failure):
    conn = published_db
    before = snapshot(conn)
    if failure == "commit":
        conn.fail_commit = True
    else:
        trigger_target = {
            "update": "UPDATE ON books",
            "delete": "DELETE ON book_characters",
            "insert": "INSERT ON book_characters",
        }[failure]
        # Test-only fault injection into the migrated temporary database.
        conn.execute(
            f"CREATE TEMP TRIGGER fail_publication BEFORE {trigger_target} "
            "BEGIN SELECT RAISE(ABORT, 'injected write failure'); END"
        )
    monkeypatch.setattr(full_builder, "summarize_book_with_characters", MagicMock(return_value=GENERATED))
    index = MagicMock()
    monkeypatch.setattr(full_builder, "index_book_summary", index)
    steps, details = [], []

    with pytest.raises(sqlite3.DatabaseError, match="injected"):
        full_builder._run_combined_step(conn, BOOK, redo=True, log=steps.append, detail=details.append)

    assert snapshot(conn) == before
    assert not conn.in_transaction
    index.assert_not_called()
    assert details == ["サマリ生成中", "生成結果を検査中"]
    assert not any("done:" in step for step in steps)


@pytest.mark.parametrize("failure", [None, "embedding", "delete", "add"])
def test_index_runs_after_visible_commit_and_failure_does_not_undo_publication(published_db, monkeypatch, failure):
    conn = published_db
    events = []
    vectors = ["old"]
    generator = MagicMock(return_value=GENERATED)
    monkeypatch.setattr(full_builder, "summarize_book_with_characters", generator)
    warning = MagicMock()
    monkeypatch.setattr(summary_index.logger, "warning", warning)

    def embed(texts):
        assert not conn.in_transaction
        with with_db() as observer:
            saved = snapshot(observer)
        assert (saved.summary, saved.catalog_summary) == GENERATED[:2]
        assert saved.characters[0].summary == "新しい人物説明"
        assert saved.summary_generated_at != "2026-01-01"
        assert saved.catalog_summary_generated_at != "2026-01-02"
        assert saved.characters[0].generated_at != "2026-01-03"
        events.append("embedding")
        assert texts == [GENERATED[0]]
        if failure == "embedding":
            raise RuntimeError("injected index failure")
        return [[1.0, 0.0]]

    def delete(_predicate):
        events.append("delete")
        if failure == "delete":
            raise RuntimeError("injected index failure")
        vectors.clear()

    def add(rows):
        events.append("add")
        if failure == "add":
            raise RuntimeError("injected index failure")
        assert rows[0]["book_name"] == BOOK
        vectors.append("new")

    table = MagicMock()
    table.delete.side_effect = delete
    table.add.side_effect = add
    monkeypatch.setattr(summary_index, "embed_batch", embed)
    monkeypatch.setattr(summary_index, "get_summaries_table", lambda: table)
    steps = []

    full_builder._run_combined_step(conn, BOOK, redo=True, log=steps.append)

    assert steps[-1] == "  done: detailed=5 chars, catalog=5 chars, 1 characters"
    expected_events = ["embedding", "delete", "add"]
    if failure:
        expected_events = expected_events[: expected_events.index(failure) + 1]
        warning.assert_called_once()
        assert str(warning.call_args.args[-1]) == "injected index failure"
    else:
        warning.assert_not_called()
    assert events == expected_events
    assert vectors == ([] if failure == "add" else ["old"] if failure else ["new"])

    # SQLite completeness drives skip; an ordinary retry does not repair the vector.
    saved = snapshot(conn)
    full_builder._run_combined_step(conn, BOOK, redo=False, log=steps.append)
    assert steps[-1] == "  skip: detailed summary, catalog summary, and characters already exist"
    assert snapshot(conn) == saved
    assert events == expected_events
    generator.assert_called_once()


@pytest.mark.parametrize(
    ("summary", "catalog", "character_summary", "skip"),
    [
        ("", "一覧", "人物", False),
        ("詳細", None, "人物", False),
        ("詳細", "一覧", None, False),
        ("詳細", "一覧", "", True),
    ],
)
def test_skip_uses_truthy_summaries_but_non_null_character_summary(
    published_db, monkeypatch, summary, catalog, character_summary, skip
):
    conn = published_db
    conn.execute("UPDATE books SET summary = ?, catalog_summary = ?", (summary, catalog))
    conn.execute("UPDATE book_characters SET summary = ?", (character_summary,))
    conn.commit()
    generator = MagicMock(return_value=GENERATED)
    monkeypatch.setattr(full_builder, "summarize_book_with_characters", generator)
    monkeypatch.setattr(full_builder, "index_book_summary", MagicMock())
    full_builder._run_combined_step(conn, BOOK, redo=False, log=lambda _: None)
    assert generator.call_count == (0 if skip else 1)


@pytest.mark.parametrize("failure", [None, "generation", "validation", "sql"])
def test_full_build_notification_order_and_failure_boundary(published_db, monkeypatch, failure):
    before = snapshot(published_db)
    events = []

    def rebuild(conn, name, *, progress_callback):
        events.append("rebuild")
        progress_callback(2, 2)

    def generate(conn, name, *, progress):
        progress("generator progress")
        if failure == "generation":
            raise ValueError("injected generation failure")
        if failure == "validation":
            return "新しい詳細", "新しい一覧", {"幻の人物": "根拠なし"}
        return GENERATED

    monkeypatch.setattr(full_builder, "rebuild_from_pages", rebuild)
    monkeypatch.setattr(full_builder, "summarize_book_with_characters", generate)
    monkeypatch.setattr(full_builder, "index_book_summary", lambda *args: events.append("index"))
    if failure == "sql":
        published_db.execute(
            "CREATE TRIGGER fail_publication BEFORE INSERT ON book_characters "
            "BEGIN SELECT RAISE(ABORT, 'injected write failure'); END"
        )
        published_db.commit()

    def run():
        full_builder.build_book_full(BOOK, redo=True, step_callback=events.append, detail_callback=events.append)

    if failure:
        with pytest.raises((ValueError, sqlite3.DatabaseError)):
            run()
        assert snapshot(published_db) == before
        assert "index" not in events
        assert "finished" not in events
    else:
        run()

    expected = [
        "start",
        "step 1/2: rebuild_from_pages",
        "rebuild",
        "embedding 2/2 チャンク",
        "step 2/2: summarize_book + characters",
        "サマリ生成中",
        "generator progress",
    ]
    endings = {
        "generation": ["  error: injected generation failure"],
        "validation": ["生成結果を検査中", "  omit character without page evidence: 幻の人物"],
        "sql": ["生成結果を検査中"],
        None: ["生成結果を検査中", "index", "  done: detailed=5 chars, catalog=5 chars, 1 characters", "finished"],
    }
    assert events == expected + endings[failure]
