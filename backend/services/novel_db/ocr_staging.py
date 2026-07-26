"""Backward-compatible OCR staging facade.

Implementation boundaries live in run storage, classification, and QA modules.
"""

from . import ocr_run_store as _ocr_run_store
from .ocr_page_classification import classify_run_pages
from .ocr_qa import (
    approve_and_publish_run,
    get_qa_image_path,
    get_qa_run,
    list_qa_runs,
    review_qa_page,
    stage_run_for_qa,
)
from .ocr_run_store import OcrInputPage, collect_input_pages, mark_run_failed, prepare_run, save_page_result

_validate_complete_run = _ocr_run_store.validate_complete_run

__all__ = [
    "OcrInputPage",
    "approve_and_publish_run",
    "classify_run_pages",
    "collect_input_pages",
    "get_qa_image_path",
    "get_qa_run",
    "list_qa_runs",
    "mark_run_failed",
    "prepare_run",
    "review_qa_page",
    "save_page_result",
    "stage_run_for_qa",
]
