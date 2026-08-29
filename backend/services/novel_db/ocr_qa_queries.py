"""Read models and source-image resolution for OCR QA."""

from __future__ import annotations

import json
from pathlib import Path

from .connection import with_db
from .ocr_run_store import collect_input_pages


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
            "qa_reviewer, qa_reviewed_at, qa_note, runtime_manifest_json, timing_json, "
            "ocr_finished_at, qa_started_at, qa_finished_at FROM ocr_runs WHERE id=?",
            (run_id,),
        ).fetchone()
        if run is None:
            raise LookupError(f"OCR run not found: {run_id}")
        pages = conn.execute(
            "SELECT page_no, state, qa_state, full_text, char_count, quality_flags_json, "
            "ink_coverage, attempt_count, error_message, qa_note, reviewed_at, "
            "page_type, index_eligible, layout_type, primary_text, external_text, "
            "selected_engine, corrected_text, selection_reason, "
            "candidate_manifest_json, processing_timing_json, "
            "review_started_at, review_duration_ms, correction_duration_ms "
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
        "runtime_manifest": json.loads(str(run[11] or "{}")),
        "timing": json.loads(str(run[12] or "{}")),
        "ocr_finished_at": run[13],
        "qa_started_at": run[14],
        "qa_finished_at": run[15],
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
                "selection_reason": row[18],
                "candidate_manifest": json.loads(str(row[19] or "{}")),
                "processing_timing": json.loads(str(row[20] or "{}")),
                "review_started_at": row[21],
                "review_duration_ms": row[22],
                "correction_duration_ms": row[23],
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
