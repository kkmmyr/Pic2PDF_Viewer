"""OCR QA review and atomic publication to canonical pages."""

from __future__ import annotations

import json
from pathlib import Path

from .connection import with_db
from .ocr_layout_types import validate_layout_type
from .ocr_page_classification import classify_run_pages
from .ocr_page_types import is_index_eligible, validate_page_type
from .ocr_qa_risk import annotate_run_qa_risks
from .ocr_run_store import OcrInputPage, collect_input_pages, validate_complete_run

_QA_AUDIT_ONLY_FLAGS = frozenset(
    {
        "cross_engine_consensus",
        "external_text_repetition",
        "primary_text_repetition",
        "sample_content_excluded",
        "yomitoku_adjudication",
    }
)


def _normalize_corrected_text(corrected_text: str | None, selected_engine: str) -> str | None:
    corrected = corrected_text if corrected_text is None else corrected_text.strip()
    if corrected and selected_engine != "codex":
        raise ValueError("corrected text requires selected engine codex")
    return corrected


def stage_run_for_qa(run_id: int, input_pages: list[OcrInputPage]) -> None:
    """Move a complete OCR run to QA without publishing canonical text."""
    validate_complete_run(run_id, input_pages)
    classify_run_pages(run_id)
    risk_pages = annotate_run_qa_risks(run_id)
    with with_db() as conn:
        current_flags = conn.execute(
            "SELECT page_no, quality_flags_json FROM ocr_page_results WHERE run_id=?",
            (run_id,),
        ).fetchall()
    flagged_pages = {
        int(row[0]) for row in current_flags if set(json.loads(str(row[1] or "[]"))) - _QA_AUDIT_ONLY_FLAGS
    }
    flagged_pages.update(risk_pages)
    page_count = len(input_pages)
    required_pages = set(range(1, min(7, page_count) + 1)) | flagged_pages
    required_pages.update({min(8, page_count), max(1, (page_count + 1) // 2), page_count})
    with with_db() as conn:
        with conn:
            conn.execute(
                "UPDATE ocr_page_results SET qa_state='not_required', qa_note=NULL, reviewed_at=NULL WHERE run_id=?",
                (run_id,),
            )
            conn.executemany(
                "UPDATE ocr_page_results SET qa_state='required' WHERE run_id=? AND page_no=?",
                [(run_id, page_no) for page_no in sorted(required_pages)],
            )
            conn.execute(
                "UPDATE ocr_page_results SET qa_state='required' WHERE run_id=? AND page_type='unknown'",
                (run_id,),
            )
            conn.execute(
                "UPDATE ocr_page_results SET qa_state='required' "
                "WHERE run_id=? AND (state!='passed' OR layout_type!='normal_prose') "
                "AND quality_flags_json NOT LIKE '%\"sample_content_excluded\"%'",
                (run_id,),
            )
            conn.execute(
                "UPDATE ocr_runs SET state='awaiting_qa', qa_state='pending', finished_at=NULL, "
                "error_message=NULL, qa_reviewer=NULL, qa_reviewed_at=NULL, qa_note=NULL WHERE id=?",
                (run_id,),
            )


def review_qa_page(
    run_id: int,
    page_no: int,
    state: str,
    note: str | None,
    page_type: str,
    layout_type: str,
    selected_engine: str,
    corrected_text: str | None,
) -> None:
    if state not in {"approved", "rejected"}:
        raise ValueError("QA page state must be approved or rejected")
    validate_page_type(page_type)
    validate_layout_type(layout_type)
    if selected_engine not in {"primary", "external", "codex"}:
        raise ValueError("selected engine must be primary, external, or codex")
    if state == "approved" and page_type == "unknown":
        raise ValueError("page type must be classified before approval")
    if state == "approved" and layout_type == "unknown":
        raise ValueError("layout type must be classified before approval")
    with with_db() as conn:
        run = conn.execute("SELECT state FROM ocr_runs WHERE id=?", (run_id,)).fetchone()
        if run is None:
            raise LookupError(f"OCR run not found: {run_id}")
        if run[0] != "awaiting_qa":
            raise ValueError("OCR run is not awaiting QA")
        page = conn.execute(
            "SELECT state, full_text, primary_text, external_text FROM ocr_page_results WHERE run_id=? AND page_no=?",
            (run_id, page_no),
        ).fetchone()
        if page is None:
            raise LookupError(f"OCR page not found: run={run_id}, page={page_no}")
        corrected = _normalize_corrected_text(corrected_text, selected_engine)
        if state == "approved" and page_type == "narrative":
            if page[0] != "passed" and not corrected:
                raise ValueError("failed narrative OCR requires reviewed corrected text")
            selected_text = {
                "primary": str(page[2] or page[1] or ""),
                "external": str(page[3] or ""),
                "codex": str(corrected or ""),
            }[selected_engine]
            if not selected_text.strip():
                raise ValueError("selected narrative text is empty")
        cursor = conn.execute(
            "UPDATE ocr_page_results SET qa_state=?, qa_note=?, page_type=?, layout_type=?, "
            "selected_engine=?, corrected_text=?, index_eligible=?, "
            "reviewed_at=datetime('now', '+9 hours') WHERE run_id=? AND page_no=?",
            (
                state,
                note,
                page_type,
                layout_type,
                selected_engine,
                corrected,
                is_index_eligible(page_type),
                run_id,
                page_no,
            ),
        )
        if cursor.rowcount != 1:
            raise LookupError(f"OCR page not found: run={run_id}, page={page_no}")
        conn.commit()


def list_qa_runs() -> list[dict]:
    with with_db() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.book_name, r.engine, r.model, r.source_page_count,
                   r.state, r.qa_state, r.started_at,
                   SUM(CASE WHEN p.qa_state='required' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN p.qa_state='approved' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN p.qa_state='rejected' THEN 1 ELSE 0 END)
            FROM ocr_runs r
            LEFT JOIN ocr_page_results p ON p.run_id=r.id
            WHERE r.state IN ('awaiting_qa', 'completed')
            GROUP BY r.id
            ORDER BY CASE WHEN r.state='awaiting_qa' THEN 0 ELSE 1 END, r.id DESC
            """
        ).fetchall()
    return [
        {
            "id": int(row[0]),
            "book_name": str(row[1]),
            "engine": str(row[2]),
            "model": str(row[3]),
            "source_page_count": int(row[4]),
            "state": str(row[5]),
            "qa_state": str(row[6]),
            "started_at": row[7],
            "required_pages": int(row[8] or 0),
            "approved_pages": int(row[9] or 0),
            "rejected_pages": int(row[10] or 0),
        }
        for row in rows
    ]


def get_qa_run(run_id: int) -> dict:
    with with_db() as conn:
        run = conn.execute(
            "SELECT id, book_name, engine, model, source_page_count, state, qa_state, started_at, "
            "qa_reviewer, qa_reviewed_at, qa_note FROM ocr_runs WHERE id=?",
            (run_id,),
        ).fetchone()
        if run is None:
            raise LookupError(f"OCR run not found: {run_id}")
        pages = conn.execute(
            "SELECT page_no, state, qa_state, full_text, char_count, quality_flags_json, "
            "ink_coverage, attempt_count, error_message, qa_note, reviewed_at, "
            "page_type, index_eligible, layout_type, primary_text, external_text, "
            "selected_engine, corrected_text "
            "FROM ocr_page_results WHERE run_id=? ORDER BY page_no",
            (run_id,),
        ).fetchall()
    required_pages = sum(row[2] == "required" for row in pages)
    approved_pages = sum(row[2] == "approved" for row in pages)
    rejected_pages = sum(row[2] == "rejected" for row in pages)
    return {
        "id": int(run[0]),
        "book_name": str(run[1]),
        "engine": str(run[2]),
        "model": str(run[3]),
        "source_page_count": int(run[4]),
        "state": str(run[5]),
        "qa_state": str(run[6]),
        "started_at": run[7],
        "qa_reviewer": run[8],
        "qa_reviewed_at": run[9],
        "qa_note": run[10],
        "required_pages": required_pages,
        "approved_pages": approved_pages,
        "rejected_pages": rejected_pages,
        "pages": [
            {
                "page_no": int(row[0]),
                "state": str(row[1]),
                "qa_state": str(row[2]),
                "full_text": str(row[3] or ""),
                "char_count": int(row[4] or 0),
                "quality_flags": json.loads(str(row[5] or "[]")),
                "ink_coverage": row[6],
                "attempt_count": int(row[7] or 0),
                "error_message": row[8],
                "qa_note": row[9],
                "reviewed_at": row[10],
                "page_type": str(row[11] or "unknown"),
                "index_eligible": bool(row[12]),
                "layout_type": str(row[13] or "unknown"),
                "primary_text": str(row[14] or row[3] or ""),
                "external_text": str(row[15] or ""),
                "selected_engine": str(row[16] or "primary"),
                "corrected_text": row[17],
                "image_url": f"/api/ocr/qa/runs/{run_id}/pages/{int(row[0])}/image",
            }
            for row in pages
        ],
    }


def get_qa_image_path(run_id: int, page_no: int) -> Path:
    with with_db() as conn:
        row = conn.execute(
            "SELECT r.book_name, p.image_sha256 FROM ocr_runs r "
            "JOIN ocr_page_results p ON p.run_id=r.id "
            "WHERE r.id=? AND p.page_no=?",
            (run_id, page_no),
        ).fetchone()
    if row is None:
        raise LookupError(f"OCR page not found: run={run_id}, page={page_no}")
    input_pages = collect_input_pages(str(row[0]))
    if page_no < 1 or page_no > len(input_pages):
        raise LookupError(f"OCR page not found: run={run_id}, page={page_no}")
    page = input_pages[page_no - 1]
    if page.image_sha256 != row[1]:
        raise ValueError(f"source image changed after OCR: page {page_no}")
    return page.image_path


def approve_and_publish_run(run_id: int, reviewer: str, note: str | None = None) -> None:
    """Publish only after every required QA page has been explicitly approved."""
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
        if int(counts[0] or 0) > 0:
            raise ValueError("required QA pages remain")
        if int(counts[1] or 0) > 0:
            raise ValueError("rejected QA pages remain")
        if int(counts[2] or 0) > 0:
            raise ValueError("unclassified OCR pages remain")
        if int(counts[3] or 0) > 0:
            raise ValueError("unclassified OCR layouts remain")
        book_name = str(run[0])

    input_pages = collect_input_pages(book_name)
    book_name, rows = validate_complete_run(run_id, input_pages)
    for row in rows:
        if row[7] != "narrative":
            continue
        corrected_text = str(row[13] or "")
        if row[2] != "passed" and not corrected_text.strip():
            raise ValueError(f"failed narrative OCR requires reviewed corrected text: page {int(row[0])}")
        selected_text = {
            "primary": str(row[10] or row[3] or ""),
            "external": str(row[11] or ""),
            "codex": corrected_text,
        }.get(str(row[12]), "")
        if not selected_text.strip():
            raise ValueError(f"selected narrative text is empty: page {int(row[0])}")
    _publish_rows(run_id, book_name, rows, input_pages, reviewer, note)


def _publish_rows(
    run_id: int,
    book_name: str,
    rows: list,
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
                selected_text = {
                    "primary": str(row[10] or row[3] or ""),
                    "external": str(row[11] or ""),
                    "codex": str(row[13] or ""),
                }.get(str(row[12]), "")
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
            conn.execute(
                "UPDATE ocr_runs SET state='completed', finished_at=datetime('now', '+9 hours'), "
                "error_message=NULL, qa_state='approved', qa_reviewer=?, "
                "qa_reviewed_at=datetime('now', '+9 hours'), qa_note=? WHERE id=?",
                (reviewer, note, run_id),
            )
