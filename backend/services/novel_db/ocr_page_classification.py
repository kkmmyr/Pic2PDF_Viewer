"""Conservative OCR page and layout classification."""

from __future__ import annotations

from .connection import with_db
from .ocr_layout_types import suggest_layout_type, validate_layout_type
from .ocr_page_types import is_index_eligible, suggest_page_type, validate_page_type


def classify_run_pages(run_id: int, *, overwrite: bool = False) -> dict[str, int]:
    """Apply conservative page-type suggestions to an OCR run."""
    with with_db() as conn:
        run = conn.execute(
            "SELECT source_page_count FROM ocr_runs WHERE id=?",
            (run_id,),
        ).fetchone()
        if run is None:
            raise LookupError(f"OCR run not found: {run_id}")
        page_count = int(run[0])
        rows = conn.execute(
            "SELECT page_no, full_text, char_count, page_type, raw_output, layout_type "
            "FROM ocr_page_results WHERE run_id=? ORDER BY page_no",
            (run_id,),
        ).fetchall()
        counts = {page_type: 0 for page_type in ("unknown", "narrative", "toc", "illustration", "colophon_or_ad")}
        with conn:
            for row in rows:
                current_type = str(row[3] or "unknown")
                page_type = (
                    suggest_page_type(
                        page_no=int(row[0]),
                        page_count=page_count,
                        full_text=str(row[1] or ""),
                        char_count=int(row[2] or 0),
                    )
                    if overwrite or current_type == "unknown"
                    else validate_page_type(current_type)
                )
                counts[page_type] += 1
                current_layout = str(row[5] or "unknown")
                suggested_layout = suggest_layout_type(
                    raw_output=str(row[4] or ""),
                    full_text=str(row[1] or ""),
                    char_count=int(row[2] or 0),
                    page_type=page_type,
                )
                layout_type = (
                    suggested_layout
                    if page_type != "narrative" or overwrite or current_layout == "unknown"
                    else validate_layout_type(current_layout)
                )
                conn.execute(
                    "UPDATE ocr_page_results SET page_type=?, layout_type=?, index_eligible=? "
                    "WHERE run_id=? AND page_no=?",
                    (page_type, layout_type, is_index_eligible(page_type), run_id, int(row[0])),
                )
            conn.execute(
                "UPDATE ocr_page_results SET qa_state='required', qa_note=NULL, reviewed_at=NULL "
                "WHERE run_id=? AND page_type='unknown'",
                (run_id,),
            )
    return counts
