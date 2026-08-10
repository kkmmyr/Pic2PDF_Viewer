"""Backward-compatible CLI facade for the OCR ground-truth benchmark.

Examples:
    uv run python scripts/maintenance/benchmark_ocr_ground_truth.py current
    uv run python scripts/maintenance/benchmark_ocr_ground_truth.py tesseract \
        --tesseract "C:/Program Files/Tesseract-OCR/tesseract.exe" \
        --tessdata-dir "C:/path/to/tessdata-best"
    uv run python scripts/maintenance/benchmark_ocr_ground_truth.py yomitoku \
        --ocr-python "D:/61.tool/common/ocr/venv/Scripts/python.exe" \
        --ocr-path "D:/61.tool/common/ocr"
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

_MAINTENANCE_DIR = Path(__file__).resolve().parent
if str(_MAINTENANCE_DIR) in sys.path:
    sys.path.remove(str(_MAINTENANCE_DIR))
sys.path.insert(0, str(_MAINTENANCE_DIR))

import ocr_benchmark_engines as _engines  # noqa: E402
from ocr_benchmark_cli import (  # noqa: E402,F401
    DEFAULT_POLICY_PATH,
    build_parser,
    main,
)
from ocr_benchmark_columns import (  # noqa: E402,F401
    _run_paddle,
    _run_paddle_columns,
    _run_surya_columns,
)
from ocr_benchmark_engines import (  # noqa: E402,F401
    _download_images,
    _flatten_ndlocr_contents,
    _is_truthy,
    _load_hypotheses_from_report,
    _run_ndlocr,
    _run_tesseract,
    _run_yomitoku,
    parse_ndlocr_payload,
)
from ocr_benchmark_gate import (  # noqa: E402,F401
    _check,
    column_gap_diagnostic,
    evaluate_quality_gate,
)
from ocr_benchmark_report import (  # noqa: E402,F401
    LAYOUT_TYPE_ORDER,
    PAGE_TYPE_ORDER,
    _print_summary,
    filter_entries,
    summarize,
)
from ocr_benchmark_text import (  # noqa: E402,F401
    NORMALIZATION_VERSION,
    _edit_distance,
    _normalize_text,
    character_error_details,
    character_error_operations,
    character_error_rate,
)

_get_json = _engines._get_json


def _run_qa_candidate(
    entries: list[dict[str, Any]], api_base: str, field: str
) -> dict[int, str]:
    """Preserve the facade's patchable HTTP seam used by existing callers/tests."""
    hypotheses: dict[int, str] = {}
    pages_by_run: dict[int, dict[int, dict[str, Any]]] = {}
    for entry in entries:
        run_id = int(entry["run_id"])
        if run_id not in pages_by_run:
            payload = _get_json(
                urljoin(api_base.rstrip("/") + "/", f"api/ocr/qa/runs/{run_id}")
            )
            pages_by_run[run_id] = {
                int(page["page_no"]): page for page in payload["pages"]
            }
        page = pages_by_run[run_id].get(int(entry["page_no"]))
        if page is None:
            raise RuntimeError(f"QA run {run_id} has no page {int(entry['page_no'])}")
        hypotheses[int(entry["id"])] = str(page.get(field) or "")
    return hypotheses


if __name__ == "__main__":
    raise SystemExit(main())
