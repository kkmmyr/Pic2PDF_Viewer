"""Compatibility contract for the legacy Surya OCR facade."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from services.novel_db import surya_parsing, surya_quality, surya_runtime, surya_server, surya_types
from services.novel_db.surya_ocr import (
    SURYA_BLOCK_PROMPT,
    SURYA_LAYOUT_PROMPT,
    SURYA_PROMPT,
    OcrSessionPolicy,
    SuryaBlock,
    SuryaClient,
    SuryaLayoutBlock,
    SuryaPageResult,
    SuryaServer,
    crosscheck_ocr_results,
    evaluate_external_ocr,
    evaluate_page_quality,
    normalize_ocr_text,
    parse_surya_html,
    parse_surya_layout,
)


def test_facade_preserves_public_symbol_identity() -> None:
    assert SURYA_BLOCK_PROMPT is surya_parsing.SURYA_BLOCK_PROMPT
    assert SURYA_LAYOUT_PROMPT is surya_parsing.SURYA_LAYOUT_PROMPT
    assert SURYA_PROMPT is surya_parsing.SURYA_PROMPT
    assert parse_surya_html is surya_parsing.parse_surya_html
    assert parse_surya_layout is surya_parsing.parse_surya_layout
    assert crosscheck_ocr_results is surya_quality.crosscheck_ocr_results
    assert evaluate_external_ocr is surya_quality.evaluate_external_ocr
    assert evaluate_page_quality is surya_quality.evaluate_page_quality
    assert normalize_ocr_text is surya_quality.normalize_ocr_text
    assert SuryaClient is surya_runtime.SuryaClient
    assert SuryaServer is surya_runtime.SuryaServer
    assert SuryaServer is surya_server.SuryaServer
    assert OcrSessionPolicy is surya_types.OcrSessionPolicy
    assert SuryaBlock is surya_types.SuryaBlock
    assert SuryaLayoutBlock is surya_types.SuryaLayoutBlock
    assert SuryaPageResult is surya_types.SuryaPageResult


def test_facade_imports_in_standalone_worker_mode() -> None:
    module_dir = Path(__file__).resolve().parents[1] / "services" / "novel_db"
    completed = subprocess.run(
        [sys.executable, "-c", "import surya_ocr; print(surya_ocr.SuryaClient.__name__)"],
        cwd=module_dir,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "SuryaClient"
