"""Generated prose snapshot, diff, and restore tests."""

from __future__ import annotations

import json

import pytest

from services.novel_db.connection import with_db
from services.novel_db.generated_content_audit import (
    GeneratedContentSnapshot,
    build_generated_content_diff,
    capture_generated_content,
    read_snapshot,
    render_diff_markdown,
    restore_generated_content,
    write_snapshot,
)
from services.novel_db.migrations import upgrade_head


@pytest.fixture
def db_conn(tmp_data_dir):
    upgrade_head()
    with with_db() as conn:
        yield conn


def _insert_generated_content(conn, *, summary: str, character_summary: str) -> int:
    cursor = conn.execute(
        """
        INSERT INTO books
            (name, pdf_path, images_dir, page_count, summary, summary_generated_at)
        VALUES ('book-10', '/book-10.pdf', '/images', 100, ?, '2026-07-01 12:00:00')
        """,
        (summary,),
    )
    book_id = int(cursor.lastrowid)
    conn.execute(
        """
        INSERT INTO book_characters
            (book_id, name, summary, first_page, page_count, generated_at)
        VALUES (?, '茉莉花', ?, 3, 80, '2026-07-01 12:00:00')
        """,
        (book_id, character_summary),
    )
    conn.commit()
    return book_id


def test_snapshot_round_trip_preserves_restorable_fields(db_conn, tmp_path):
    _insert_generated_content(
        db_conn,
        summary="茉莉花は事件を調べ、その原因を明らかにする。",
        character_summary="茉莉花は官吏として事件を調べる主人公である。",
    )

    snapshot = capture_generated_content(
        db_conn,
        "book-10",
        captured_at="2026-07-28T00:00:00+00:00",
    )
    path = tmp_path / "snapshot.json"
    write_snapshot(path, snapshot)

    assert read_snapshot(path) == snapshot
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["characters"][0]["first_page"] == 3


def test_diff_reports_full_summary_and_character_changes(db_conn):
    book_id = _insert_generated_content(
        db_conn,
        summary="茉莉花は事件を調べ、その原因を明らかにする。",
        character_summary="茉莉花は官吏として事件を調べる主人公である。",
    )
    before = capture_generated_content(db_conn, "book-10")
    db_conn.execute(
        "UPDATE books SET summary = ?, summary_generated_at = '2026-07-28 20:00:00' WHERE id = ?",
        ("茉莉花は事件の背景を調べ、仲間と協力して真相へ到達する。", book_id),
    )
    db_conn.execute("DELETE FROM book_characters WHERE book_id = ?", (book_id,))
    db_conn.executemany(
        """
        INSERT INTO book_characters
            (book_id, name, summary, first_page, page_count, generated_at)
        VALUES (?, ?, ?, ?, ?, '2026-07-28 20:00:00')
        """,
        [
            (book_id, "茉莉花", "茉莉花は官吏として仲間と事件の真相を追う主人公である。", 3, 82),
            (book_id, "珀陽", "珀陽は茉莉花を支え、調査の進展に力を貸す人物である。", 8, 40),
        ],
    )
    db_conn.commit()

    after = capture_generated_content(db_conn, "book-10")
    report = build_generated_content_diff(before, after)

    assert report["summary_change"]["changed"] is True
    assert report["character_changes"]["added"] == ["珀陽"]
    assert [item["name"] for item in report["character_changes"]["changed"]] == ["茉莉花"]
    assert report["quality"]["passed"] is True
    markdown = render_diff_markdown(report)
    assert "## 要約（変更前）" in markdown
    assert "## 人物: 茉莉花" in markdown
    assert after.summary in markdown


def test_diff_fails_mechanical_gate_for_marker_and_missing_subject(db_conn):
    book_id = _insert_generated_content(
        db_conn,
        summary="以前の要約。",
        character_summary="茉莉花は主人公である。",
    )
    before = capture_generated_content(db_conn, "book-10")
    db_conn.execute("UPDATE books SET summary = '[SUMMARY] leaked' WHERE id = ?", (book_id,))
    db_conn.execute(
        "UPDATE book_characters SET summary = '官吏として事件を調べる。' WHERE book_id = ?",
        (book_id,),
    )
    db_conn.commit()

    report = build_generated_content_diff(
        before,
        capture_generated_content(db_conn, "book-10"),
    )

    assert report["quality"]["passed"] is False
    assert report["quality"]["summary_issues"]
    assert "茉莉花" in report["quality"]["character_issues"]


def test_restore_requires_exact_confirmation_and_is_transactional(db_conn):
    book_id = _insert_generated_content(
        db_conn,
        summary="旧要約。",
        character_summary="茉莉花は旧版の主人公である。",
    )
    before = capture_generated_content(db_conn, "book-10")
    db_conn.execute("UPDATE books SET summary = '新版要約。' WHERE id = ?", (book_id,))
    db_conn.execute("DELETE FROM book_characters WHERE book_id = ?", (book_id,))
    db_conn.commit()

    with pytest.raises(ValueError, match="exactly match"):
        restore_generated_content(db_conn, before, confirmed_book_name="book")

    restored_id, restored_summary = restore_generated_content(
        db_conn,
        before,
        confirmed_book_name="book-10",
    )

    assert restored_id == book_id
    assert restored_summary == "旧要約。"
    restored = capture_generated_content(db_conn, "book-10")
    assert restored == GeneratedContentSnapshot(
        schema_version=before.schema_version,
        captured_at=restored.captured_at,
        book_name=before.book_name,
        summary=before.summary,
        summary_generated_at=before.summary_generated_at,
        characters=before.characters,
    )


def test_read_snapshot_rejects_unknown_schema(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"schema_version": 99}', encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported snapshot schema"):
        read_snapshot(path)
