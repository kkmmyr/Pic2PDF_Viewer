"""Validation and persistence for one OCR QA page review."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from .connection import with_db
from .ocr_layout_types import validate_layout_type
from .ocr_page_types import is_index_eligible, validate_page_type

_QA_PAGE_STATES = frozenset({"approved", "rejected"})
_SELECTED_ENGINES = frozenset({"primary", "external", "codex"})


def _normalize_corrected_text(corrected_text: str | None, selected_engine: str) -> str | None:
    corrected = corrected_text if corrected_text is None else corrected_text.strip()
    if corrected and selected_engine != "codex":
        raise ValueError("corrected text requires selected engine codex")
    return corrected


def _validate_review_request(
    state: str,
    page_type: str,
    layout_type: str,
    selected_engine: str,
) -> None:
    if state not in _QA_PAGE_STATES:
        raise ValueError("QA page state must be approved or rejected")
    validate_page_type(page_type)
    validate_layout_type(layout_type)
    if selected_engine not in _SELECTED_ENGINES:
        raise ValueError("selected engine must be primary, external, or codex")
    if state == "approved" and page_type == "unknown":
        raise ValueError("page type must be classified before approval")
    if state == "approved" and layout_type == "unknown":
        raise ValueError("layout type must be classified before approval")


def _validate_narrative_selection(
    page: sqlite3.Row,
    state: str,
    page_type: str,
    selected_engine: str,
    corrected_text: str | None,
) -> None:
    if state != "approved" or page_type != "narrative":
        return
    if page[0] != "passed" and not corrected_text:
        raise ValueError("failed narrative OCR requires reviewed corrected text")
    selected_text = {
        "primary": str(page[2] or page[1] or ""),
        "external": str(page[3] or ""),
        "codex": str(corrected_text or ""),
    }[selected_engine]
    if not selected_text.strip():
        raise ValueError("selected narrative text is empty")


def review_qa_page(
    run_id: int,
    page_no: int,
    state: str,
    note: str | None,
    page_type: str,
    layout_type: str,
    selected_engine: str,
    corrected_text: str | None,
    review_started_at: str | None = None,
    review_duration_ms: int | None = None,
    correction_duration_ms: int | None = None,
) -> None:
    _validate_review_request(state, page_type, layout_type, selected_engine)
    if review_started_at is not None:
        try:
            datetime.fromisoformat(review_started_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("review started at must be an ISO-8601 timestamp") from exc
    for label, duration in (
        ("review duration", review_duration_ms),
        ("correction duration", correction_duration_ms),
    ):
        if duration is not None and (isinstance(duration, bool) or duration < 0):
            raise ValueError(f"{label} must be non-negative milliseconds")
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
        _validate_narrative_selection(page, state, page_type, selected_engine, corrected)
        cursor = conn.execute(
            "UPDATE ocr_page_results SET qa_state=?, qa_note=?, page_type=?, layout_type=?, "
            "selected_engine=?, corrected_text=?, index_eligible=?, "
            "review_started_at=?, review_duration_ms=?, correction_duration_ms=?, "
            "reviewed_at=datetime('now', '+9 hours') WHERE run_id=? AND page_no=?",
            (
                state,
                note,
                page_type,
                layout_type,
                selected_engine,
                corrected,
                is_index_eligible(page_type),
                review_started_at,
                review_duration_ms,
                correction_duration_ms if selected_engine == "codex" else None,
                run_id,
                page_no,
            ),
        )
        if cursor.rowcount != 1:
            raise LookupError(f"OCR page not found: run={run_id}, page={page_no}")
        conn.commit()
