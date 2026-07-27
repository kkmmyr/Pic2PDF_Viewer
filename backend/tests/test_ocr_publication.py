from __future__ import annotations

import sqlite3

from services.novel_db.connection import with_db
from services.novel_db.migrations import upgrade_head
from services.novel_db.ocr_publication import list_current_published_runs
from services.novel_db.ocr_qa_risk import audit_current_published_repetitions

_REPEATED_TEXT = "\n".join(["これは十分に長い反復文章の一行です。"] * 3)
_CLEAN_TEXT = "これは公開中の正常な本文で、同じ長文行の反復はありません。"


def _insert_run(
    conn: sqlite3.Connection,
    *,
    book_name: str,
    state: str,
    qa_state: str,
    reviewed_at: str,
    text: str,
) -> int:
    cursor = conn.execute(
        "INSERT INTO ocr_runs "
        "(book_name, engine, model, source_page_count, state, started_at, "
        "finished_at, qa_state, qa_reviewed_at) "
        "VALUES (?, 'surya2', 'test-model', 1, ?, ?, ?, ?, ?)",
        (
            book_name,
            state,
            reviewed_at,
            reviewed_at,
            qa_state,
            reviewed_at,
        ),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("failed to allocate OCR run id")
    run_id = cursor.lastrowid
    conn.execute(
        "INSERT INTO ocr_page_results "
        "(run_id, page_no, image_sha256, state, full_text, char_count, "
        "primary_text, selected_engine) "
        "VALUES (?, 1, 'sha', 'passed', ?, ?, ?, 'primary')",
        (run_id, text, len(text), text),
    )
    return run_id


def test_publication_audit_uses_only_latest_approved_run_per_book(tmp_data_dir) -> None:
    upgrade_head()
    with with_db() as conn:
        old_approved = _insert_run(
            conn,
            book_name="book-a",
            state="completed",
            qa_state="approved",
            reviewed_at="2026-07-01 10:00:00",
            text=_REPEATED_TEXT,
        )
        current_approved = _insert_run(
            conn,
            book_name="book-a",
            state="completed",
            qa_state="approved",
            reviewed_at="2026-07-02 10:00:00",
            text=_CLEAN_TEXT,
        )
        pending = _insert_run(
            conn,
            book_name="book-a",
            state="awaiting_qa",
            qa_state="pending",
            reviewed_at="2026-07-03 10:00:00",
            text=_REPEATED_TEXT,
        )
        repeated_current = _insert_run(
            conn,
            book_name="book-b",
            state="completed",
            qa_state="approved",
            reviewed_at="2026-07-02 12:00:00",
            text=_REPEATED_TEXT,
        )
        conn.commit()

        published = list_current_published_runs(conn)
        assert [(run.book_name, run.id) for run in published] == [
            ("book-a", current_approved),
            ("book-b", repeated_current),
        ]

        risks = audit_current_published_repetitions(conn)
        assert [(risk.run_id, risk.book_name, risk.sources) for risk in risks] == [
            (repeated_current, "book-b", ("primary", "selected"))
        ]
        assert old_approved not in {risk.run_id for risk in risks}
        assert pending not in {risk.run_id for risk in risks}


def test_publication_selection_breaks_equal_timestamp_ties_by_run_id(tmp_data_dir) -> None:
    upgrade_head()
    with with_db() as conn:
        first = _insert_run(
            conn,
            book_name="book-tie",
            state="completed",
            qa_state="approved",
            reviewed_at="2026-07-02 10:00:00",
            text=_REPEATED_TEXT,
        )
        second = _insert_run(
            conn,
            book_name="book-tie",
            state="completed",
            qa_state="approved",
            reviewed_at="2026-07-02 10:00:00",
            text=_CLEAN_TEXT,
        )
        conn.commit()

        published = list_current_published_runs(conn, book_names=["book-tie"])
        assert first < second
        assert [run.id for run in published] == [second]
        assert list_current_published_runs(conn, book_names=[]) == []
