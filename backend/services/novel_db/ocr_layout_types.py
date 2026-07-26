"""OCR layout classification independent from semantic page types."""

from __future__ import annotations

import re

LAYOUT_TYPES = frozenset(
    {
        "unknown",
        "normal_prose",
        "full_width",
        "mixed_illustration",
        "structured",
        "image_only",
    }
)

_LABEL_RE = re.compile(r'data-label=["\']([^"\']+)["\']', re.IGNORECASE)
_BBOX_RE = re.compile(r'data-bbox=["\']([^"\']+)["\']', re.IGNORECASE)
_NON_TEXT_LABELS = frozenset({"picture", "image", "figure", "diagram"})
_STRUCTURED_LABELS = frozenset({"table", "table-of-contents", "formula", "handwriting"})


def validate_layout_type(layout_type: str) -> str:
    if layout_type not in LAYOUT_TYPES:
        allowed = ", ".join(sorted(LAYOUT_TYPES))
        raise ValueError(f"invalid OCR layout type: {layout_type}; expected one of {allowed}")
    return layout_type


def suggest_layout_type(
    *,
    raw_output: str | None,
    full_text: str | None,
    char_count: int,
    page_type: str = "unknown",
) -> str:
    """Return a conservative layout suggestion from persisted OCR evidence."""
    normalized_count = max(char_count, len(re.sub(r"\s+", "", full_text or "")))
    labels = {label.strip().lower() for label in _LABEL_RE.findall(raw_output or "")}

    if page_type == "toc" or labels & _STRUCTURED_LABELS:
        return "structured"
    if page_type in {"illustration", "colophon_or_ad"} and normalized_count < 80:
        return "image_only"
    if labels & _NON_TEXT_LABELS and normalized_count >= 30:
        return "mixed_illustration"

    # A single broad text block is unlike the narrow vertical columns used by
    # ordinary prose. Keep it as a review-required suggestion.
    broad_blocks = 0
    for bbox_text in _BBOX_RE.findall(raw_output or ""):
        try:
            x0, _y0, x1, _y1 = (float(value) for value in bbox_text.split())
        except (TypeError, ValueError):
            continue
        if x1 - x0 >= 650:
            broad_blocks += 1
    if normalized_count >= 100 and broad_blocks == 1:
        return "full_width"
    if normalized_count >= 300:
        return "normal_prose"
    if normalized_count < 30:
        return "image_only"
    return "unknown"
