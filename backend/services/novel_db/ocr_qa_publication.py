"""Approval guards and atomic publication for OCR QA runs."""

from __future__ import annotations

import sqlite3

from .connection import with_db
from .ocr_run_store import OcrInputPage, collect_input_pages, validate_complete_run
from .page_fts import mark_page_fts_stale


def _validate_approval_counts(counts: sqlite3.Row) -> None:
    if int(counts[0] or 0) > 0:
        raise ValueError("required QA pages remain")
    if int(counts[1] or 0) > 0:
        raise ValueError("rejected QA pages remain")
    if int(counts[2] or 0) > 0:
        raise ValueError("unclassified OCR pages remain")
    if int(counts[3] or 0) > 0:
        raise ValueError("unclassified OCR layouts remain")


def _load_approval_book_name(run_id: int) -> str:
    with with_db() as conn:
        run = conn.execute(
            "SELECT book_name, state FROM ocr_runs WHERE id=?",
            (run_id,),
        ).fetchone()
        if run is None:
            raise LookupError(f"OCR run not found: {run_id}")
        if run[1] != "awaiting_qa":
            raise ValueError("OCR run is not awaiting QA")
        counts = conn.execute(
            "SELECT "
            "SUM(CASE WHEN qa_state='required' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN qa_state='rejected' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN page_type='unknown' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN layout_type='unknown' THEN 1 ELSE 0 END) "
            "FROM ocr_page_results WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if counts is None:
            raise RuntimeError(f"failed to count OCR pages: run={run_id}")
        _validate_approval_counts(counts)
        return str(run[0])


def _selected_text(row: sqlite3.Row) -> str:
    return {
        "primary": str(row[10] or row[3] or ""),
        "external": str(row[11] or ""),
        "codex": str(row[13] or ""),
    }.get(str(row[12]), "")


def _validate_publishable_rows(rows: list[sqlite3.Row]) -> None:
    for row in rows:
        if row[7] != "narrative":
            continue
        corrected_text = str(row[13] or "")
        if row[2] != "passed" and not corrected_text.strip():
            raise ValueError(f"failed narrative OCR requires reviewed corrected text: page {int(row[0])}")
        if not _selected_text(row).strip():
            raise ValueError(f"selected narrative text is empty: page {int(row[0])}")


def approve_and_publish_run(run_id: int, reviewer: str, note: str | None = None) -> None:
    """Publish only after every required QA page has been explicitly approved."""
    book_name = _load_approval_book_name(run_id)
    input_pages = collect_input_pages(book_name)
    validated_book_name, rows = validate_complete_run(run_id, input_pages)
    _validate_publishable_rows(rows)
    _publish_rows(run_id, validated_book_name, rows, input_pages, reviewer, note)


def _publish_rows(
    run_id: int,
    book_name: str,
    rows: list[sqlite3.Row],
    input_pages: list[OcrInputPage],
    reviewer: str,
    note: str | None,
) -> None:
    """Atomically publish validated rows and mark the run QA-approved."""
    with with_db() as conn:
        images_dir = input_pages[0].image_path.parent
        with conn:
            existing = conn.execute("SELECT id FROM books WHERE name = ?", (book_name,)).fetchone()
            if existing is None:
                cursor = conn.execute(
                    "INSERT INTO books "
                    "(name, pdf_path, images_dir, page_count, indexed_at, ocr_done_at) "
                    "VALUES (?, '', ?, ?, NULL, datetime('now', '+9 hours'))",
                    (book_name, str(images_dir), len(input_pages)),
                )
                if cursor.lastrowid is None:
                    raise RuntimeError("failed to create book during OCR publication")
                book_id = cursor.lastrowid
            else:
                book_id = int(existing[0])
                conn.execute(
                    "UPDATE books SET images_dir=?, page_count=?, indexed_at=NULL, "
                    "ocr_done_at=datetime('now', '+9 hours') WHERE id=?",
                    (str(images_dir), len(input_pages), book_id),
                )

            for row in rows:
                page_no = int(row[0])
                image_path = input_pages[page_no - 1].image_path
                page_type = str(row[7])
                selected_text = _selected_text(row)
                published_text = selected_text if page_type == "narrative" else ""
                conn.execute(
                    """
                    INSERT INTO pages (
                        book_id, page_no, image_path, full_text, char_count,
                        page_type, index_eligible
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(book_id, page_no) DO UPDATE SET
                        image_path=excluded.image_path,
                        full_text=excluded.full_text,
                        char_count=excluded.char_count,
                        page_type=excluded.page_type,
                        index_eligible=excluded.index_eligible
                    """,
                    (
                        book_id,
                        page_no,
                        str(image_path),
                        published_text,
                        len(published_text),
                        page_type,
                        bool(row[8]),
                    ),
                )
            conn.execute(
                "DELETE FROM pages WHERE book_id=? AND page_no > ?",
                (book_id, len(input_pages)),
            )
            conn.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild')")
            mark_page_fts_stale(conn)
            conn.execute(
                "UPDATE ocr_runs SET state='completed', finished_at=datetime('now', '+9 hours'), "
                "error_message=NULL, qa_state='approved', qa_reviewer=?, "
                "qa_reviewed_at=datetime('now', '+9 hours'), qa_note=? WHERE id=?",
                (reviewer, note, run_id),
            )
