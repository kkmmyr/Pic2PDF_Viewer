"""Ground-truth-independent OCR candidate selection predicates."""

from __future__ import annotations

import re

from .ocr_content_guards import has_suspicious_repetition

_WHITESPACE_RE = re.compile(r"\s+")
_MIN_PRIMARY_LENGTH_FOR_COMPLETENESS = 256
_MIN_EXTERNAL_LENGTH_ADVANTAGE = 30
_MIN_EXTERNAL_LENGTH_RATIO = 1.02
_MIN_EXTERNAL_LENGTH_FOR_REPETITION_FALLBACK = 256


def is_external_safe_repetition_fallback(
    primary_text: str,
    external_text: str,
) -> bool:
    """Return whether external can replace a catastrophically repeated primary."""
    external_compact = _WHITESPACE_RE.sub("", external_text)
    return (
        has_suspicious_repetition(primary_text)
        and len(external_compact) >= _MIN_EXTERNAL_LENGTH_FOR_REPETITION_FALLBACK
        and not has_suspicious_repetition(external_text)
    )


def is_external_materially_more_complete(
    primary_text: str,
    external_text: str,
) -> bool:
    """Return whether external preserves materially more text than primary."""
    primary_compact = _WHITESPACE_RE.sub("", primary_text)
    external_compact = _WHITESPACE_RE.sub("", external_text)
    external_advantage = len(external_compact) - len(primary_compact)
    return (
        len(primary_compact) >= _MIN_PRIMARY_LENGTH_FOR_COMPLETENESS
        and external_advantage >= _MIN_EXTERNAL_LENGTH_ADVANTAGE
        and len(external_compact) >= len(primary_compact) * _MIN_EXTERNAL_LENGTH_RATIO
    )
