"""Transition complete OCR runs into explicit QA review."""

from __future__ import annotations

from .connection import with_db
from .ocr_page_classification import classify_run_pages
from .ocr_qa_risk import annotate_run_qa_risks
from .ocr_run_store import OcrInputPage, validate_complete_run, validate_run_provenance


def stage_run_for_qa(run_id: int, input_pages: list[OcrInputPage]) -> None:
    """Move a complete OCR run to QA without publishing canonical text."""
    validate_complete_run(run_id, input_pages)
    validate_run_provenance(run_id)
    classify_run_pages(run_id)
    annotate_run_qa_risks(run_id)
    with with_db() as conn:
        with conn:
            conn.execute(
                "UPDATE ocr_page_results SET qa_state='required', qa_note=NULL, reviewed_at=NULL, "
                "review_started_at=NULL, review_duration_ms=NULL, correction_duration_ms=NULL WHERE run_id=?",
                (run_id,),
            )
            conn.execute(
                "UPDATE ocr_runs SET state='awaiting_qa', qa_state='pending', finished_at=NULL, "
                "ocr_finished_at=datetime('now', '+9 hours'), qa_started_at=datetime('now', '+9 hours'), "
                "qa_finished_at=NULL, error_message=NULL, qa_reviewer=NULL, qa_reviewed_at=NULL, "
                "qa_note=NULL WHERE id=?",
                (run_id,),
            )
