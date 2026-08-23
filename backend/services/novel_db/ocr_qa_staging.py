"""Transition complete OCR runs into explicit QA review."""

from __future__ import annotations

import json

from .connection import with_db
from .ocr_page_classification import classify_run_pages
from .ocr_qa_risk import annotate_run_qa_risks
from .ocr_run_store import OcrInputPage, validate_complete_run

_QA_AUDIT_ONLY_FLAGS = frozenset(
    {
        "cross_engine_consensus",
        "external_text_repetition",
        "primary_text_repetition",
        "sample_content_excluded",
        "yomitoku_adjudication",
    }
)
_RISK_SCOPED_REVIEW_ENGINES = frozenset({"qwen35_dots_review_v1"})
_REVIEW_ASSISTED_AUDIT_ONLY_FLAGS = frozenset(
    {
        "candidate_disagreement",
        "review_assisted_composite",
        "selection_reason:qwen_clean",
    }
)


def stage_run_for_qa(run_id: int, input_pages: list[OcrInputPage]) -> None:
    """Move a complete OCR run to QA without publishing canonical text."""
    validate_complete_run(run_id, input_pages)
    classify_run_pages(run_id)
    risk_pages = annotate_run_qa_risks(run_id)
    with with_db() as conn:
        run = conn.execute("SELECT engine FROM ocr_runs WHERE id=?", (run_id,)).fetchone()
        if run is None:
            raise LookupError(f"OCR run not found: {run_id}")
        risk_scoped_review = str(run[0]) in _RISK_SCOPED_REVIEW_ENGINES
        current_flags = conn.execute(
            "SELECT page_no, quality_flags_json FROM ocr_page_results WHERE run_id=?",
            (run_id,),
        ).fetchall()
    audit_only_flags = _QA_AUDIT_ONLY_FLAGS
    if risk_scoped_review:
        audit_only_flags |= _REVIEW_ASSISTED_AUDIT_ONLY_FLAGS
    flagged_pages = {int(row[0]) for row in current_flags if set(json.loads(str(row[1] or "[]"))) - audit_only_flags}
    flagged_pages.update(risk_pages)
    page_count = len(input_pages)
    if risk_scoped_review:
        required_pages = flagged_pages | {max(1, (page_count + 1) // 2)}
    else:
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
