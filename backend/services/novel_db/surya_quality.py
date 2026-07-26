"""Surya OCR結果の品質評価と外部OCR照合。"""

from __future__ import annotations

import re
from dataclasses import replace
from difflib import SequenceMatcher
from html import escape
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

try:
    from .surya_parsing import parse_surya_html
    from .surya_types import SuryaBlock, SuryaPageResult
except ImportError:  # Standalone ``python ocr_worker.py`` execution.
    from surya_parsing import parse_surya_html
    from surya_types import SuryaBlock, SuryaPageResult

NON_TEXT_LABELS = {
    "picture",
    "image",
    "figure",
    "diagram",
    "blankpage",
    "blank-page",
}
STRUCTURED_COVERAGE_LABELS = NON_TEXT_LABELS | {
    "caption",
    "table",
    "table-of-contents",
}
_JAPANESE_CHAR_CLASS = r"\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff"
_REPEATED_PHRASE_RE = re.compile(r"(.{12,80})\1{3,}", re.DOTALL)

QUALITY_HARD_FLAGS = {
    "invalid_bbox",
    "no_blocks",
    "empty_text",
    "low_ink_coverage",
    "duplicate_text_block",
    "excessive_text",
    "repeated_text",
    "malformed_output",
}


def is_valid_bbox(bbox: tuple[float, float, float, float]) -> bool:
    x0, y0, x1, y1 = bbox
    return 0 <= x0 < x1 <= 1000 and 0 <= y0 < y1 <= 1000


def _ink_coverage(
    image: Image.Image,
    blocks: list[SuryaBlock],
) -> tuple[float | None, int]:
    # Kindleページは一様な黒背景も使うため、暗画素ではなく局所edgeを測る。
    edges = np.asarray(image.convert("L").filter(ImageFilter.FIND_EDGES))
    ink = edges > 32
    ink[:2, :] = False
    ink[-2:, :] = False
    ink[:, :2] = False
    ink[:, -2:] = False
    ink_count = int(np.count_nonzero(ink))
    if ink_count < 100:
        return None, ink_count

    height, width = edges.shape
    covered = np.zeros_like(ink, dtype=bool)
    for block in blocks:
        if not is_valid_bbox(block.bbox):
            continue
        x0, y0, x1, y1 = block.bbox
        left = max(0, min(width, int(np.floor(x0 * width / 1000))))
        top = max(0, min(height, int(np.floor(y0 * height / 1000))))
        right = max(0, min(width, int(np.ceil(x1 * width / 1000))))
        bottom = max(0, min(height, int(np.ceil(y1 * height / 1000))))
        covered[top:bottom, left:right] = True
    return float(np.count_nonzero(ink & covered) / ink_count), ink_count


def evaluate_page_quality(
    image: Image.Image,
    raw_output: str,
    *,
    min_ink_coverage: float,
    attempt_count: int,
) -> SuryaPageResult:
    blocks = parse_surya_html(raw_output)
    flags: list[str] = []
    invalid_count = sum(not is_valid_bbox(block.bbox) for block in blocks)
    if invalid_count:
        flags.append("invalid_bbox")

    text_parts = [block.text for block in blocks if block.text]
    full_text = "\n".join(text_parts)
    normalized_blocks = [re.sub(r"\s+", "", block.text) for block in blocks if block.text]
    long_blocks = [text for text in normalized_blocks if len(text) >= 20]
    if len(long_blocks) != len(set(long_blocks)):
        flags.append("duplicate_text_block")
    compact_text = re.sub(r"\s+", "", full_text)
    if len(compact_text) > 6000:
        flags.append("excessive_text")
    if _REPEATED_PHRASE_RE.search(compact_text):
        flags.append("repeated_text")
    coverage, ink_count = _ink_coverage(image, blocks)
    labels = {block.label.casefold() for block in blocks}
    is_blank = ink_count < 100
    is_non_text_page = bool(labels & NON_TEXT_LABELS) and not full_text

    if not blocks:
        if is_blank:
            flags.append("blank_page")
        else:
            flags.append("no_blocks")
            if raw_output.strip():
                flags.append("malformed_output")
    elif not full_text:
        if is_blank:
            flags.append("blank_page")
        elif is_non_text_page:
            flags.append("non_text_page")
        else:
            flags.append("empty_text")

    if coverage is not None and coverage < min_ink_coverage and not is_non_text_page:
        flags.append("low_ink_coverage")

    failed = bool(QUALITY_HARD_FLAGS.intersection(flags))
    return SuryaPageResult(
        full_text=full_text,
        raw_output=raw_output,
        blocks=blocks,
        state="failed" if failed else "passed",
        quality_flags=flags,
        ink_coverage=coverage,
        attempt_count=attempt_count,
        error_message=", ".join(flags) if failed else None,
    )


def evaluate_external_ocr(
    image: Image.Image,
    items: list[dict[str, Any]],
    *,
    min_ink_coverage: float,
    attempt_count: int,
    engine_flag: str,
    min_median_confidence: float = 0.85,
    min_weighted_mean_confidence: float = 0.75,
    max_low_confidence_char_ratio: float = 0.25,
    low_confidence_threshold: float = 0.5,
) -> SuryaPageResult:
    """副OCR結果を正規化し、confidence分布を評価する。"""
    width, height = image.size
    html_blocks: list[str] = []
    confidence_samples: list[tuple[float, int]] = []
    for item in items:
        text = str(item.get("text", "")).strip()
        text = re.sub(
            rf"(?<=[{_JAPANESE_CHAR_CLASS}]) +(?=[{_JAPANESE_CHAR_CLASS}、。！？])",
            "",
            text,
        )
        position = item.get("position")
        if not text or position is None:
            continue
        try:
            points = np.asarray(position, dtype=float)
            if points.shape == (4, 2):
                x0, y0 = points.min(axis=0)
                x1, y1 = points.max(axis=0)
            elif points.size == 4:
                x0, y0, x1, y1 = points.reshape(-1)
            else:
                continue
            bbox = (
                float(x0) * 1000 / width,
                float(y0) * 1000 / height,
                float(x1) * 1000 / width,
                float(y1) * 1000 / height,
            )
            if not is_valid_bbox(bbox):
                continue
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            continue
        confidence_samples.append((confidence, len(text)))
        bbox_text = " ".join(f"{value:g}" for value in bbox)
        inner = escape(text, quote=False).replace("\n", "<br/>")
        html_blocks.append(f'<div data-label="Text" data-bbox="{bbox_text}">{inner}</div>')

    result = evaluate_page_quality(
        image,
        "\n".join(html_blocks),
        min_ink_coverage=min_ink_coverage,
        attempt_count=attempt_count,
    )
    result = replace(result, quality_flags=[*result.quality_flags, engine_flag])
    if not confidence_samples:
        flags = [*result.quality_flags, "external_ocr_low_confidence"]
        return replace(
            result,
            state="failed",
            quality_flags=flags,
            error_message="external_ocr_low_confidence",
        )
    confidences = np.asarray(
        [sample[0] for sample in confidence_samples],
        dtype=float,
    )
    weights = np.asarray([sample[1] for sample in confidence_samples], dtype=float)
    median_confidence = float(np.median(confidences))
    weighted_mean_confidence = float(np.average(confidences, weights=weights))
    low_confidence_char_ratio = float(weights[confidences < low_confidence_threshold].sum() / weights.sum())
    distribution_passed = (
        median_confidence >= min_median_confidence
        and weighted_mean_confidence >= min_weighted_mean_confidence
        and low_confidence_char_ratio <= max_low_confidence_char_ratio
    )
    if not distribution_passed:
        flags = [*result.quality_flags, "external_ocr_low_confidence"]
        return replace(
            result,
            state="failed",
            quality_flags=flags,
            error_message="external_ocr_low_confidence",
        )
    if min(confidences) < min_median_confidence:
        result = replace(
            result,
            quality_flags=[
                *result.quality_flags,
                "external_ocr_distribution_accepted",
            ],
        )
    remaining = set(result.quality_flags) - {"low_ink_coverage", engine_flag}
    remaining.discard("external_ocr_distribution_accepted")
    if result.state == "failed" and not remaining and result.full_text and result.char_count <= 256:
        flags = [*result.quality_flags, "external_ocr_confidence_exempt"]
        return replace(
            result,
            state="passed",
            quality_flags=flags,
            error_message=None,
        )
    return result


def normalize_ocr_text(text: str) -> str:
    """独立OCR結果を比較する前にlayout由来の差だけを正規化する。"""
    return re.sub(r"\s+", "", text)


def add_quality_flag(result: SuryaPageResult, flag: str) -> SuryaPageResult:
    if flag in result.quality_flags:
        return result
    return replace(result, quality_flags=[*result.quality_flags, flag])


def crosscheck_ocr_results(
    primary: SuryaPageResult,
    external: SuryaPageResult,
    *,
    min_similarity: float = 0.85,
    more_complete_ratio: float = 1.02,
) -> SuryaPageResult:
    """不一致を隠さず、独立した2つのOCR結果を裁定する。"""
    if external.state != "passed":
        if primary.state == "passed":
            return add_quality_flag(primary, "external_crosscheck_unavailable")
        return external
    if primary.state != "passed":
        return add_quality_flag(external, "external_ocr_recovered_primary")

    primary_text = normalize_ocr_text(primary.full_text)
    external_text = normalize_ocr_text(external.full_text)
    if not primary_text or not external_text:
        flags = [*primary.quality_flags, "cross_engine_disagreement"]
        return replace(
            primary,
            state="failed",
            quality_flags=flags,
            error_message="cross_engine_disagreement",
        )

    similarity = SequenceMatcher(
        None,
        primary_text,
        external_text,
        autojunk=False,
    ).ratio()
    if similarity < min_similarity:
        flags = [*primary.quality_flags, "cross_engine_disagreement"]
        return replace(
            primary,
            state="failed",
            quality_flags=flags,
            error_message="cross_engine_disagreement",
        )

    if len(external_text) / len(primary_text) >= more_complete_ratio:
        return add_quality_flag(external, "external_ocr_more_complete")
    return add_quality_flag(primary, "cross_engine_consensus")
