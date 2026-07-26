"""Surya OCRの互換公開facade。

型、解析、品質評価、推論runtimeは責務別moduleへ分割する。既存importはこのmoduleで
維持し、OCR algorithm・threshold・公開objectを変更しない。
"""

try:
    from .surya_parsing import (
        SURYA_BLOCK_PROMPT,
        SURYA_LAYOUT_PROMPT,
        SURYA_PROMPT,
        parse_surya_html,
        parse_surya_layout,
    )
    from .surya_quality import (
        crosscheck_ocr_results,
        evaluate_external_ocr,
        evaluate_page_quality,
        normalize_ocr_text,
    )
    from .surya_runtime import SuryaClient, SuryaServer
    from .surya_types import (
        OcrSessionPolicy,
        SuryaBlock,
        SuryaLayoutBlock,
        SuryaPageResult,
    )
except ImportError:  # Standalone ``python ocr_worker.py`` execution.
    from surya_parsing import (
        SURYA_BLOCK_PROMPT,
        SURYA_LAYOUT_PROMPT,
        SURYA_PROMPT,
        parse_surya_html,
        parse_surya_layout,
    )
    from surya_quality import (
        crosscheck_ocr_results,
        evaluate_external_ocr,
        evaluate_page_quality,
        normalize_ocr_text,
    )
    from surya_runtime import SuryaClient, SuryaServer
    from surya_types import (
        OcrSessionPolicy,
        SuryaBlock,
        SuryaLayoutBlock,
        SuryaPageResult,
    )

__all__ = [
    "SURYA_BLOCK_PROMPT",
    "SURYA_LAYOUT_PROMPT",
    "SURYA_PROMPT",
    "OcrSessionPolicy",
    "SuryaBlock",
    "SuryaClient",
    "SuryaLayoutBlock",
    "SuryaPageResult",
    "SuryaServer",
    "crosscheck_ocr_results",
    "evaluate_external_ocr",
    "evaluate_page_quality",
    "normalize_ocr_text",
    "parse_surya_html",
    "parse_surya_layout",
]
