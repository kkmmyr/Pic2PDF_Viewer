"""Surya OCR 2 client, output parser, and page quality gate.

This module intentionally uses only the Python standard library, Pillow, and
NumPy so it can run in the isolated OCR interpreter as well as backend tests.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

SURYA_PROMPT = (
    "OCR this image to HTML. Each block is a div with data-label and data-bbox (x0 y0 x1 y1, normalized 0-1000)."
)
SURYA_LAYOUT_PROMPT = (
    'Output the layout of this image as JSON. Each entry is a dict with "label", "bbox", and "count" fields. '
    "Bbox is x0 y0 x1 y1, normalized 0-1000."
)
SURYA_BLOCK_PROMPT = "OCR this block image to HTML."
_NON_TEXT_LABELS = {"picture", "image", "figure", "diagram", "blankpage", "blank-page"}
_SKIP_BLOCK_OCR_LABELS = {"image", "figure", "diagram", "blank-page", "blankpage"}
_STRUCTURED_COVERAGE_LABELS = _NON_TEXT_LABELS | {"caption", "table", "table-of-contents"}
_CODE_FENCE_RE = re.compile(r"^\s*```(?:html)?\s*|\s*```\s*$", re.IGNORECASE)
_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)
_BBOX_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_JAPANESE_CHAR_CLASS = r"\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff"
_REPEATED_PHRASE_RE = re.compile(r"(.{12,80})\1{3,}", re.DOTALL)

_LAYOUT_MAX_TOKENS = 3072
_BLOCK_MAX_TOKENS = 8192
_FULL_PAGE_MAX_TOKENS = 12288


@dataclass(frozen=True)
class SuryaBlock:
    label: str
    bbox: tuple[float, float, float, float]
    text: str


@dataclass(frozen=True)
class SuryaLayoutBlock:
    label: str
    bbox: tuple[float, float, float, float]
    count: int


@dataclass(frozen=True)
class SuryaPageResult:
    full_text: str
    raw_output: str
    blocks: list[SuryaBlock]
    state: str
    quality_flags: list[str]
    ink_coverage: float | None
    attempt_count: int
    error_message: str | None = None

    @property
    def char_count(self) -> int:
        return len(self.full_text)


@dataclass
class _BlockBuilder:
    label: str
    bbox: tuple[float, float, float, float] | None
    text_parts: list[str]


class _SuryaHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._builders: list[_BlockBuilder] = []
        self._tag_stack: list[str] = []
        self.blocks: list[SuryaBlock] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        self._tag_stack.append(tag)
        if tag == "div":
            values = {key.lower(): value or "" for key, value in attrs}
            self._builders.append(
                _BlockBuilder(
                    label=values.get("data-label", "Text"),
                    bbox=_parse_bbox(values.get("data-bbox", "")),
                    text_parts=[],
                )
            )
        elif tag == "br" and self._builders:
            self._builders[-1].text_parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self._tag_stack:
            self._tag_stack.pop()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "div" and self._builders:
            builder = self._builders.pop()
            if builder.bbox is not None:
                self.blocks.append(
                    SuryaBlock(
                        label=builder.label,
                        bbox=builder.bbox,
                        text=_normalize_block_text("".join(builder.text_parts)),
                    )
                )
        for index in range(len(self._tag_stack) - 1, -1, -1):
            if self._tag_stack[index] == tag:
                del self._tag_stack[index]
                break

    def handle_data(self, data: str) -> None:
        if self._builders and "rt" not in self._tag_stack:
            self._builders[-1].text_parts.append(data)


def _parse_bbox(value: str) -> tuple[float, float, float, float] | None:
    numbers = [float(item) for item in _BBOX_NUMBER_RE.findall(value)]
    if len(numbers) != 4:
        return None
    return numbers[0], numbers[1], numbers[2], numbers[3]


def _normalize_block_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\t\f\v ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_surya_html(raw_output: str) -> list[SuryaBlock]:
    """Parse official Surya GGUF div output and discard ruby ``rt`` text."""
    parser = _SuryaHtmlParser()
    parser.feed(_CODE_FENCE_RE.sub("", raw_output.strip()))
    parser.close()
    return parser.blocks


def parse_surya_layout(raw_output: str) -> list[SuryaLayoutBlock]:
    """Parse Surya's layout-task JSON, including accidental task drift output."""
    if parse_surya_html(raw_output):
        return []
    cleaned = _CODE_FENCE_RE.sub("", raw_output.strip())
    match = _JSON_ARRAY_RE.search(cleaned)
    if match is None:
        return []
    try:
        payload = json.loads(match.group(0))
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []

    blocks: list[SuryaLayoutBlock] = []
    for item in payload:
        if not isinstance(item, dict) or "label" not in item or "bbox" not in item:
            return []
        bbox_value = item["bbox"]
        bbox = _parse_bbox(str(bbox_value))
        if bbox is None:
            return []
        try:
            count = max(0, int(item.get("count", 0)))
        except (TypeError, ValueError):
            count = 0
        blocks.append(SuryaLayoutBlock(label=str(item["label"]), bbox=bbox, count=count))
    return blocks


def _is_valid_bbox(bbox: tuple[float, float, float, float]) -> bool:
    x0, y0, x1, y1 = bbox
    return 0 <= x0 < x1 <= 1000 and 0 <= y0 < y1 <= 1000


def _ink_coverage(image: Image.Image, blocks: list[SuryaBlock]) -> tuple[float | None, int]:
    # Measure local contrast rather than dark pixels.  Kindle pages can use a
    # solid black background; counting that background as ink makes coverage
    # meaningless even when every white glyph is inside an OCR bbox.
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
        if not _is_valid_bbox(block.bbox):
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
    invalid_count = sum(not _is_valid_bbox(block.bbox) for block in blocks)
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
    is_non_text_page = bool(labels & _NON_TEXT_LABELS) and not full_text

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

    hard_flags = {
        "invalid_bbox",
        "no_blocks",
        "empty_text",
        "low_ink_coverage",
        "duplicate_text_block",
        "excessive_text",
        "repeated_text",
        "malformed_output",
    }
    failed = bool(hard_flags.intersection(flags))
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
    min_confidence: float = 0.9,
) -> SuryaPageResult:
    """Normalize a high-confidence secondary OCR result through the same gate."""
    width, height = image.size
    html_blocks: list[str] = []
    confidences: list[float] = []
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
            if not _is_valid_bbox(bbox):
                continue
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            continue
        confidences.append(confidence)
        bbox_text = " ".join(f"{value:g}" for value in bbox)
        inner = escape(text, quote=False).replace("\n", "<br/>")
        html_blocks.append(f'<div data-label="Text" data-bbox="{bbox_text}">{inner}</div>')

    raw_output = "\n".join(html_blocks)
    result = evaluate_page_quality(
        image,
        raw_output,
        min_ink_coverage=min_ink_coverage,
        attempt_count=attempt_count,
    )
    result = replace(result, quality_flags=[*result.quality_flags, engine_flag])
    if not confidences or min(confidences) < min_confidence:
        flags = [*result.quality_flags, "external_ocr_low_confidence"]
        return replace(
            result,
            state="failed",
            quality_flags=flags,
            error_message="external_ocr_low_confidence",
        )
    remaining = set(result.quality_flags) - {"low_ink_coverage", engine_flag}
    if result.state == "failed" and not remaining and result.full_text and result.char_count <= 256:
        flags = [*result.quality_flags, "external_ocr_high_confidence_exempt"]
        return replace(result, state="passed", quality_flags=flags, error_message=None)
    return result


class SuryaServer:
    """Connect to an existing llama-server or own one for the worker lifetime."""

    def __init__(
        self,
        base_url: str,
        *,
        executable: str | None = None,
        model_path: str | None = None,
        mmproj_path: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.executable = executable
        self.model_path = model_path
        self.mmproj_path = mmproj_path
        self._process: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> SuryaServer:
        if self._healthy():
            return self
        self._start_owned_server()
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if self._process is not None and self._process.poll() is not None:
                raise RuntimeError(f"llama-server exited with code {self._process.returncode}")
            if self._healthy():
                return self
            time.sleep(1)
        self.close()
        raise TimeoutError("llama-server did not become ready within 120 seconds")

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()

    def close(self) -> None:
        if self._process is None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)
        self._process = None

    def _healthy(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/models", timeout=2) as response:
                return response.status == 200
        except (OSError, urllib.error.URLError):
            return False

    def _start_owned_server(self) -> None:
        paths = [self.executable, self.model_path, self.mmproj_path]
        if not all(paths):
            raise RuntimeError(
                "Surya server is unavailable. Set SURYA_LLAMA_SERVER_PATH, "
                "SURYA_MODEL_PATH, and SURYA_MMPROJ_PATH for automatic startup."
            )
        assert self.executable and self.model_path and self.mmproj_path
        for path in paths:
            if not Path(str(path)).is_file():
                raise FileNotFoundError(f"Surya runtime file not found: {path}")

        parsed = urlparse(self.base_url)
        if parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError("automatic llama-server startup requires a localhost SURYA_INFERENCE_URL")
        port = parsed.port or 8768
        cmd = [
            self.executable,
            "--model",
            self.model_path,
            "--mmproj",
            self.mmproj_path,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--ctx-size",
            "16384",
            "--parallel",
            "1",
            "--gpu-layers",
            "99",
            "--image-min-tokens",
            "1024",
            "--jinja",
        ]
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self._process = subprocess.Popen(
            cmd,
            stdout=sys.stderr,
            stderr=sys.stderr,
            creationflags=creationflags,
        )


class SuryaClient:
    def __init__(self, base_url: str, model: str, timeout_sec: float, min_ink_coverage: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_sec = timeout_sec
        self.min_ink_coverage = min_ink_coverage

    def recognize_with_quality(self, image: Image.Image, max_attempts: int) -> SuryaPageResult:
        variants = self._variants(image)
        candidates: list[SuryaPageResult] = []
        last_error: Exception | None = None
        for attempt, candidate_image in enumerate(variants[: max(1, max_attempts)], start=1):
            try:
                raw_output = self._recognize(candidate_image)
                layout = parse_surya_layout(raw_output)
                used_block_fallback = bool(layout)
                if layout:
                    raw_output = self._recognize_layout_blocks(candidate_image, layout)
                result = evaluate_page_quality(
                    candidate_image,
                    raw_output,
                    min_ink_coverage=self.min_ink_coverage,
                    attempt_count=attempt,
                )
                if used_block_fallback:
                    result = self._add_quality_flag(result, "layout_block_fallback")
                candidates.append(result)
                if result.state == "passed":
                    return result
                if {"malformed_output", "repeated_text", "excessive_text"}.intersection(result.quality_flags):
                    return result
            except Exception as exc:
                last_error = exc

        # A structurally valid full-page result can still miss decorated text.
        # Use Surya's official two-stage layout -> block OCR path as the final,
        # high-quality fallback instead of weakening the global coverage gate.
        fallback_attempt = min(max(1, max_attempts), len(variants)) + 1
        try:
            layout_raw = self._recognize(
                image,
                prompt=SURYA_LAYOUT_PROMPT,
                max_tokens=_LAYOUT_MAX_TOKENS,
            )
            layout = parse_surya_layout(layout_raw)
            if not layout:
                layout = self._layout_from_ocr_blocks(parse_surya_html(layout_raw))
            if not layout and candidates:
                best_candidate = max(candidates, key=lambda item: (item.ink_coverage or 0.0, item.char_count))
                layout = self._layout_from_ocr_blocks(best_candidate.blocks)
            if layout:
                raw_output = self._recognize_layout_blocks(image, layout)
                result = evaluate_page_quality(
                    image,
                    raw_output,
                    min_ink_coverage=self.min_ink_coverage,
                    attempt_count=fallback_attempt,
                )
                result = self._add_quality_flag(result, "layout_block_fallback")
                candidates.append(result)
                if result.state == "passed":
                    return result
        except Exception as exc:
            last_error = exc

        if candidates:
            best = max(candidates, key=self._candidate_score)
            structured = self._accept_structured_coverage(best)
            if structured.state == "passed":
                return structured
            sparse = self._accept_sparse_page(best, candidates)
            if sparse.state == "passed" and any("duplicate_text_block" in item.quality_flags for item in candidates):
                sparse = self._add_quality_flag(sparse, "duplicate_text_recovery")
            return sparse
        message = str(last_error) if last_error else "Surya OCR returned no result"
        return SuryaPageResult(
            full_text="",
            raw_output="",
            blocks=[],
            state="failed",
            quality_flags=["request_error"],
            ink_coverage=None,
            attempt_count=min(max_attempts, len(variants)),
            error_message=message,
        )

    def _recognize(
        self,
        image: Image.Image,
        *,
        prompt: str = SURYA_PROMPT,
        max_tokens: int = _FULL_PAGE_MAX_TOKENS,
    ) -> str:
        image_bytes = io.BytesIO()
        image.convert("RGB").save(image_bytes, format="PNG")
        encoded = base64.b64encode(image_bytes.getvalue()).decode("ascii")
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "temperature": 0,
            "top_p": 0.1,
            "max_tokens": max_tokens,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
            data: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        raise ValueError("Surya response content is not text")

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
            if _is_valid_bbox(block.bbox) and block.label.casefold() not in _SKIP_BLOCK_OCR_LABELS:
                left = max(0, min(width, int(np.floor(x0 * width / 1000))))
                top = max(0, min(height, int(np.floor(y0 * height / 1000))))
                right = max(0, min(width, int(np.ceil(x1 * width / 1000))))
                bottom = max(0, min(height, int(np.ceil(y1 * height / 1000))))
                if right > left and bottom > top:
                    crop = image.crop((left, top, right, bottom))
                    block_raw = self._recognize(
                        crop,
                        prompt=SURYA_BLOCK_PROMPT,
                        max_tokens=min(max(block.count + 100, 64), _BLOCK_MAX_TOKENS),
                    ).strip()
                    if parse_surya_layout(block_raw):
                        raise ValueError("Surya block OCR returned layout JSON")
                    inner_html = _CODE_FENCE_RE.sub(
                        "",
                        block_raw,
                    )
            html_blocks.append(f'<div data-label="{label}" data-bbox="{bbox_text}">{inner_html}</div>')
        return "\n".join(html_blocks)

    @staticmethod
    def _add_quality_flag(result: SuryaPageResult, flag: str) -> SuryaPageResult:
        if flag in result.quality_flags:
            return result
        return replace(result, quality_flags=[*result.quality_flags, flag])

    @staticmethod
    def _layout_from_ocr_blocks(blocks: list[SuryaBlock]) -> list[SuryaLayoutBlock]:
        return [
            SuryaLayoutBlock(
                label=block.label,
                bbox=block.bbox,
                count=max(50, len(block.text) * 2),
            )
            for block in blocks
        ]

    @staticmethod
    def _accept_structured_coverage(result: SuryaPageResult) -> SuryaPageResult:
        remaining_hard_flags = set(result.quality_flags) - {"low_ink_coverage", "layout_block_fallback"}
        labels = {block.label.casefold() for block in result.blocks}
        if (
            result.state == "failed"
            and not remaining_hard_flags
            and result.full_text
            and len(result.blocks) >= 2
            and bool(labels & _STRUCTURED_COVERAGE_LABELS)
        ):
            flags = [*result.quality_flags, "structured_page_coverage_exempt"]
            return replace(result, state="passed", quality_flags=flags, error_message=None)
        return result

    @staticmethod
    def _candidate_score(result: SuryaPageResult) -> tuple[int, float, int]:
        hard_flags = {
            "invalid_bbox",
            "no_blocks",
            "empty_text",
            "low_ink_coverage",
            "duplicate_text_block",
            "excessive_text",
            "repeated_text",
            "malformed_output",
        }
        failure_count = len(hard_flags.intersection(result.quality_flags))
        return -failure_count, result.ink_coverage or 0.0, result.char_count

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
                if other and SequenceMatcher(None, normalized, other, autojunk=False).ratio() >= 0.98:
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
        """Match Surya's 28px-grid, 3072x2048 total-pixel preprocessing contract."""
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
