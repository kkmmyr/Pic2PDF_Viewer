"""Surya llama-server lifecycle and inference client."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from html import escape

import numpy as np
from PIL import Image, ImageEnhance

try:
    from .surya_parsing import (
        CODE_FENCE_RE,
        SURYA_BLOCK_PROMPT,
        SURYA_LAYOUT_PROMPT,
        SURYA_PROMPT,
        parse_surya_html,
        parse_surya_layout,
    )
    from .surya_quality import (
        QUALITY_HARD_FLAGS,
        STRUCTURED_COVERAGE_LABELS,
        add_quality_flag,
        evaluate_page_quality,
        is_valid_bbox,
    )
    from .surya_server import SuryaServer as SuryaServer
    from .surya_transport import SuryaTransport
    from .surya_types import SuryaBlock, SuryaLayoutBlock, SuryaPageResult
except ImportError:  # Standalone ``python ocr_worker.py`` execution.
    from surya_parsing import (
        CODE_FENCE_RE,
        SURYA_BLOCK_PROMPT,
        SURYA_LAYOUT_PROMPT,
        SURYA_PROMPT,
        parse_surya_html,
        parse_surya_layout,
    )
    from surya_quality import (
        QUALITY_HARD_FLAGS,
        STRUCTURED_COVERAGE_LABELS,
        add_quality_flag,
        evaluate_page_quality,
        is_valid_bbox,
    )
    from surya_server import SuryaServer as SuryaServer
    from surya_transport import SuryaTransport
    from surya_types import SuryaBlock, SuryaLayoutBlock, SuryaPageResult

_SKIP_BLOCK_OCR_LABELS = {
    "image",
    "figure",
    "diagram",
    "blank-page",
    "blankpage",
}
_LAYOUT_MAX_TOKENS = 3072
_BLOCK_MAX_TOKENS = 8192
_FULL_PAGE_MAX_TOKENS = 12288


@dataclass
class _VariantOutcome:
    candidates: list[SuryaPageResult]
    last_error: Exception | None = None
    terminal: SuryaPageResult | None = None


class SuryaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_sec: float,
        min_ink_coverage: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_sec = timeout_sec
        self.min_ink_coverage = min_ink_coverage
        self._transport = SuryaTransport(self.base_url, self.model, timeout_sec)

    def recognize_with_quality(
        self,
        image: Image.Image,
        max_attempts: int,
    ) -> SuryaPageResult:
        variants = self._variants(image)
        outcome = self._recognize_variants(
            variants,
            max_attempts=max_attempts,
        )
        if outcome.terminal is not None:
            return outcome.terminal
        fallback_attempt = min(max(1, max_attempts), len(variants)) + 1
        self._recognize_fallback(
            image,
            outcome,
            fallback_attempt=fallback_attempt,
        )
        if outcome.terminal is not None:
            return outcome.terminal
        if outcome.candidates:
            return self._select_best_candidate(outcome.candidates)
        return self._request_failure(
            outcome.last_error,
            max_attempts=max_attempts,
            variant_count=len(variants),
        )

    def _recognize_variants(
        self,
        variants: list[Image.Image],
        *,
        max_attempts: int,
    ) -> _VariantOutcome:
        outcome = _VariantOutcome(candidates=[])
        for attempt, candidate_image in enumerate(
            variants[: max(1, max_attempts)],
            start=1,
        ):
            try:
                raw_output = self._recognize(candidate_image)
                layout = parse_surya_layout(raw_output)
                used_block_fallback = bool(layout)
                if layout:
                    raw_output = self._recognize_layout_blocks(
                        candidate_image,
                        layout,
                    )
                result = evaluate_page_quality(
                    candidate_image,
                    raw_output,
                    min_ink_coverage=self.min_ink_coverage,
                    attempt_count=attempt,
                )
                if used_block_fallback:
                    result = self._add_quality_flag(
                        result,
                        "layout_block_fallback",
                    )
                outcome.candidates.append(result)
                if result.state == "passed":
                    outcome.terminal = result
                    return outcome
                if {
                    "malformed_output",
                    "repeated_text",
                    "excessive_text",
                }.intersection(result.quality_flags):
                    outcome.terminal = result
                    return outcome
            except Exception as exc:
                outcome.last_error = exc
        return outcome

    def _recognize_fallback(
        self,
        image: Image.Image,
        outcome: _VariantOutcome,
        *,
        fallback_attempt: int,
    ) -> None:
        try:
            layout_raw = self._recognize(
                image,
                prompt=SURYA_LAYOUT_PROMPT,
                max_tokens=_LAYOUT_MAX_TOKENS,
            )
            layout = parse_surya_layout(layout_raw)
            if not layout:
                layout = self._layout_from_ocr_blocks(parse_surya_html(layout_raw))
            if not layout and outcome.candidates:
                best_candidate = max(
                    outcome.candidates,
                    key=lambda item: (
                        item.ink_coverage or 0.0,
                        item.char_count,
                    ),
                )
                layout = self._layout_from_ocr_blocks(best_candidate.blocks)
            if layout:
                raw_output = self._recognize_layout_blocks(image, layout)
                result = evaluate_page_quality(
                    image,
                    raw_output,
                    min_ink_coverage=self.min_ink_coverage,
                    attempt_count=fallback_attempt,
                )
                result = self._add_quality_flag(
                    result,
                    "layout_block_fallback",
                )
                outcome.candidates.append(result)
                if result.state == "passed":
                    outcome.terminal = result
        except Exception as exc:
            outcome.last_error = exc

    def _select_best_candidate(
        self,
        candidates: list[SuryaPageResult],
    ) -> SuryaPageResult:
        best = max(candidates, key=self._candidate_score)
        structured = self._accept_structured_coverage(best)
        if structured.state == "passed":
            return structured
        sparse = self._accept_sparse_page(best, candidates)
        has_duplicate = any("duplicate_text_block" in item.quality_flags for item in candidates)
        if sparse.state == "passed" and has_duplicate:
            return self._add_quality_flag(sparse, "duplicate_text_recovery")
        return sparse

    @staticmethod
    def _request_failure(
        last_error: Exception | None,
        *,
        max_attempts: int,
        variant_count: int,
    ) -> SuryaPageResult:
        message = str(last_error) if last_error else "Surya OCR returned no result"
        return SuryaPageResult(
            full_text="",
            raw_output="",
            blocks=[],
            state="failed",
            quality_flags=["request_error"],
            ink_coverage=None,
            attempt_count=min(max_attempts, variant_count),
            error_message=message,
        )

    def _recognize(
        self,
        image: Image.Image,
        *,
        prompt: str = SURYA_PROMPT,
        max_tokens: int = _FULL_PAGE_MAX_TOKENS,
    ) -> str:
        return self._transport.recognize(
            image,
            prompt=prompt,
            max_tokens=max_tokens,
        )

    def _recognize_layout_blocks(
        self,
        image: Image.Image,
        layout: list[SuryaLayoutBlock],
    ) -> str:
        width, height = image.size
        html_blocks: list[str] = []
        for block in layout:
            x0, y0, x1, y1 = block.bbox
            bbox_text = " ".join(f"{value:g}" for value in block.bbox)
            label = escape(block.label, quote=True)
            inner_html = ""
            if is_valid_bbox(block.bbox) and block.label.casefold() not in _SKIP_BLOCK_OCR_LABELS:
                left = max(
                    0,
                    min(width, int(np.floor(x0 * width / 1000))),
                )
                top = max(
                    0,
                    min(height, int(np.floor(y0 * height / 1000))),
                )
                right = max(
                    0,
                    min(width, int(np.ceil(x1 * width / 1000))),
                )
                bottom = max(
                    0,
                    min(height, int(np.ceil(y1 * height / 1000))),
                )
                if right > left and bottom > top:
                    crop = image.crop((left, top, right, bottom))
                    block_raw = self._recognize(
                        crop,
                        prompt=SURYA_BLOCK_PROMPT,
                        max_tokens=min(
                            max(block.count + 100, 64),
                            _BLOCK_MAX_TOKENS,
                        ),
                    ).strip()
                    if parse_surya_layout(block_raw):
                        raise ValueError("Surya block OCR returned layout JSON")
                    inner_html = CODE_FENCE_RE.sub("", block_raw)
            html_blocks.append(f'<div data-label="{label}" data-bbox="{bbox_text}">{inner_html}</div>')
        return "\n".join(html_blocks)

    @staticmethod
    def _add_quality_flag(
        result: SuryaPageResult,
        flag: str,
    ) -> SuryaPageResult:
        return add_quality_flag(result, flag)

    @staticmethod
    def _layout_from_ocr_blocks(
        blocks: list[SuryaBlock],
    ) -> list[SuryaLayoutBlock]:
        return [
            SuryaLayoutBlock(
                label=block.label,
                bbox=block.bbox,
                count=max(50, len(block.text) * 2),
            )
            for block in blocks
        ]

    @staticmethod
    def _accept_structured_coverage(
        result: SuryaPageResult,
    ) -> SuryaPageResult:
        remaining_hard_flags = set(result.quality_flags) - {
            "low_ink_coverage",
            "layout_block_fallback",
        }
        labels = {block.label.casefold() for block in result.blocks}
        if (
            result.state == "failed"
            and not remaining_hard_flags
            and result.full_text
            and len(result.blocks) >= 2
            and bool(labels & STRUCTURED_COVERAGE_LABELS)
        ):
            flags = [
                *result.quality_flags,
                "structured_page_coverage_exempt",
            ]
            return replace(
                result,
                state="passed",
                quality_flags=flags,
                error_message=None,
            )
        return result

    @staticmethod
    def _candidate_score(
        result: SuryaPageResult,
    ) -> tuple[int, float, int]:
        failure_count = len(QUALITY_HARD_FLAGS.intersection(result.quality_flags))
        return (
            -failure_count,
            result.ink_coverage or 0.0,
            result.char_count,
        )

    @staticmethod
    def _accept_sparse_page(
        result: SuryaPageResult,
        candidates: list[SuryaPageResult],
    ) -> SuryaPageResult:
        allowed_flags = {"low_ink_coverage", "layout_block_fallback"}
        if (
            result.state != "failed"
            or not result.full_text
            or result.char_count > 256
            or not set(result.quality_flags).issubset(allowed_flags)
        ):
            return result

        reason: str | None = None
        if "layout_block_fallback" in result.quality_flags:
            reason = "sparse_page_block_fallback"
        else:
            normalized = re.sub(r"\s+", "", result.full_text)
            for candidate in candidates:
                if candidate is result or set(candidate.quality_flags) - allowed_flags:
                    continue
                other = re.sub(r"\s+", "", candidate.full_text)
                if (
                    other
                    and SequenceMatcher(
                        None,
                        normalized,
                        other,
                        autojunk=False,
                    ).ratio()
                    >= 0.98
                ):
                    reason = "sparse_page_variant_consensus"
                    break
        if reason is None:
            return result
        return replace(
            result,
            state="passed",
            quality_flags=[*result.quality_flags, reason],
            error_message=None,
        )

    @staticmethod
    def _variants(image: Image.Image) -> list[Image.Image]:
        original = image.convert("RGB")
        resized = SuryaClient._scale_to_fit(original)
        variants = [resized]
        if resized.size != original.size:
            variants.append(original)
        variants.append(ImageEnhance.Contrast(resized).enhance(1.2))
        return variants

    @staticmethod
    def _scale_to_fit(image: Image.Image) -> Image.Image:
        """Suryaの28px grid・3072x2048総pixel前処理契約へ合わせる。"""
        width, height = image.size
        if width <= 0 or height <= 0:
            return image
        max_pixels = 3072 * 2048
        min_pixels = 1792 * 28
        current_pixels = width * height
        scale = 1.0
        if current_pixels > max_pixels:
            scale = (max_pixels / current_pixels) ** 0.5
        elif current_pixels < min_pixels:
            scale = (min_pixels / current_pixels) ** 0.5

        original_aspect = width / height
        width_blocks = max(1, round(width * scale / 28))
        height_blocks = max(1, round(height * scale / 28))
        while width_blocks * height_blocks * 28 * 28 > max_pixels:
            if width_blocks == 1:
                height_blocks -= 1
            elif height_blocks == 1:
                width_blocks -= 1
            else:
                width_loss = abs((width_blocks - 1) / height_blocks - original_aspect)
                height_loss = abs(width_blocks / (height_blocks - 1) - original_aspect)
                if width_loss < height_loss:
                    width_blocks -= 1
                else:
                    height_blocks -= 1

        target = (width_blocks * 28, height_blocks * 28)
        if target == image.size:
            return image
        return image.resize(target, Image.Resampling.LANCZOS)
