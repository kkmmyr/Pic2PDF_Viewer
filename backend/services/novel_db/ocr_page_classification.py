"""Conservative OCR page and layout classification."""

from __future__ import annotations

import json

from .connection import with_db
from .ocr_content_guards import detect_sample_boundary
from .ocr_layout_types import suggest_layout_type, validate_layout_type
from .ocr_page_types import is_index_eligible, suggest_page_type, validate_page_type

_MANAGED_BOUNDARY_FLAGS = frozenset({"sample_content_boundary", "sample_content_excluded"})


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
            "SELECT page_no, full_text, char_count, page_type, raw_output, layout_type, "
            "quality_flags_json "
            "FROM ocr_page_results WHERE run_id=? ORDER BY page_no",
            (run_id,),
        ).fetchall()
        sample_boundary = detect_sample_boundary(
            [(int(row[0]), str(row[1] or "")) for row in rows],
            page_count=page_count,
        )
        counts = {page_type: 0 for page_type in ("unknown", "narrative", "toc", "illustration", "colophon_or_ad")}
        with conn:
            for row in rows:
                page_no = int(row[0])
                current_type = str(row[3] or "unknown")
                if sample_boundary is not None and page_no >= sample_boundary:
                    page_type = "colophon_or_ad"
                else:
                    page_type = (
                        suggest_page_type(
                            page_no=page_no,
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
                quality_flags = set(json.loads(str(row[6] or "[]"))) - _MANAGED_BOUNDARY_FLAGS
                if sample_boundary is not None:
                    if page_no == sample_boundary:
                        quality_flags.add("sample_content_boundary")
                    elif page_no > sample_boundary:
                        quality_flags.add("sample_content_excluded")
                conn.execute(
                    "UPDATE ocr_page_results SET page_type=?, layout_type=?, index_eligible=?, "
                    "quality_flags_json=? "
                    "WHERE run_id=? AND page_no=?",
                    (
                        page_type,
                        layout_type,
                        is_index_eligible(page_type),
                        json.dumps(sorted(quality_flags), ensure_ascii=False),
                        run_id,
                        page_no,
                    ),
                )
            conn.execute(
                "UPDATE ocr_page_results SET qa_state='required', qa_note=NULL, reviewed_at=NULL "
                "WHERE run_id=? AND page_type='unknown'",
                (run_id,),
            )
    return counts
