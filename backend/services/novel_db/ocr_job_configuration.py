"""Composition adapter for the OCR job's engine and model revision."""

import config

from .ocr_job_application import OcrRunSpec
from .qwen_dots_worker import COMPOSITE_MODEL_REVISION


def resolve_ocr_run_spec() -> OcrRunSpec:
    """Read current settings when an OCR job starts preparing its runs."""
    engine = config.app_settings.OCR_ENGINE.casefold()
    if engine == "surya2":
        model = config.app_settings.SURYA_MODEL_REVISION
    elif engine == "qwen35_dots_review_v1":
        model = COMPOSITE_MODEL_REVISION
    else:
        model = engine
    return OcrRunSpec(engine=engine, model_revision=model)
