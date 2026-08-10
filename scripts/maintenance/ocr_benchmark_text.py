"""Text normalization and deterministic OCR edit metrics."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

NORMALIZATION_VERSION = "nfkc-whitespace-dash-v1"
_DASH_TRANSLATION = str.maketrans({dash: "―" for dash in "‐‑‒–—―"})


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).translate(_DASH_TRANSLATION)
    normalized = normalized.replace("...", "…")
    return re.sub(r"\s+", "", normalized)


def _edit_distance(reference: str, hypothesis: str) -> int:
    previous = list(range(len(hypothesis) + 1))
    for row_index, reference_char in enumerate(reference, start=1):
        current = [row_index]
        for column_index, hypothesis_char in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column_index] + 1,
                    previous[column_index - 1] + (reference_char != hypothesis_char),
                )
            )
        previous = current
    return previous[-1]


def character_error_rate(
    reference: str, hypothesis: str
) -> tuple[int, int, float | None]:
    normalized_reference = _normalize_text(reference)
    normalized_hypothesis = _normalize_text(hypothesis)
    distance = _edit_distance(normalized_reference, normalized_hypothesis)
    reference_chars = len(normalized_reference)
    return (
        distance,
        reference_chars,
        distance / reference_chars if reference_chars else None,
    )


def _build_edit_trace(reference: str, hypothesis: str) -> tuple[list[bytearray], int]:
    """Build the deterministic trace shared by count and operation reports."""
    row_count = len(reference)
    column_count = len(hypothesis)
    directions = [bytearray(column_count + 1) for _ in range(row_count + 1)]
    for column_index in range(1, column_count + 1):
        directions[0][column_index] = 3
    previous = list(range(column_count + 1))
    for row_index, reference_char in enumerate(reference, start=1):
        current = [row_index]
        directions[row_index][0] = 2
        for column_index, hypothesis_char in enumerate(hypothesis, start=1):
            substitution = previous[column_index - 1] + (
                reference_char != hypothesis_char
            )
            deletion = previous[column_index] + 1
            insertion = current[column_index - 1] + 1
            if substitution <= deletion and substitution <= insertion:
                current.append(substitution)
                directions[row_index][column_index] = 1
            elif deletion <= insertion:
                current.append(deletion)
                directions[row_index][column_index] = 2
            else:
                current.append(insertion)
                directions[row_index][column_index] = 3
        previous = current
    return directions, previous[column_count]


def character_error_details(
    reference: str, hypothesis: str
) -> dict[str, int | float | None]:
    """Return deterministic Levenshtein operation counts for omission screening."""
    normalized_reference = _normalize_text(reference)
    normalized_hypothesis = _normalize_text(hypothesis)
    row_count = len(normalized_reference)
    column_count = len(normalized_hypothesis)
    directions, distance = _build_edit_trace(
        normalized_reference, normalized_hypothesis
    )

    substitutions = deletions = insertions = 0
    row_index = row_count
    column_index = column_count
    while row_index or column_index:
        direction = directions[row_index][column_index]
        if direction == 1:
            substitutions += int(
                normalized_reference[row_index - 1]
                != normalized_hypothesis[column_index - 1]
            )
            row_index -= 1
            column_index -= 1
        elif direction == 2:
            deletions += 1
            row_index -= 1
        else:
            insertions += 1
            column_index -= 1

    return {
        "edit_distance": distance,
        "reference_chars": row_count,
        "cer": distance / row_count if row_count else None,
        "substitutions": substitutions,
        "deletions": deletions,
        "insertions": insertions,
        "deletion_rate": deletions / row_count if row_count else None,
    }


def character_error_operations(reference: str, hypothesis: str) -> list[dict[str, Any]]:
    """Return exact edit operations with normalized-text indexes and local context."""
    normalized_reference = _normalize_text(reference)
    normalized_hypothesis = _normalize_text(hypothesis)
    row_count = len(normalized_reference)
    column_count = len(normalized_hypothesis)
    directions, _distance = _build_edit_trace(
        normalized_reference, normalized_hypothesis
    )

    operations = []
    row_index = row_count
    column_index = column_count
    while row_index or column_index:
        direction = directions[row_index][column_index]
        if direction == 1:
            reference_char = normalized_reference[row_index - 1]
            hypothesis_char = normalized_hypothesis[column_index - 1]
            if reference_char != hypothesis_char:
                operations.append(
                    {
                        "operation": "substitution",
                        "reference_index": row_index - 1,
                        "hypothesis_index": column_index - 1,
                        "reference_char": reference_char,
                        "hypothesis_char": hypothesis_char,
                    }
                )
            row_index -= 1
            column_index -= 1
        elif direction == 2:
            operations.append(
                {
                    "operation": "deletion",
                    "reference_index": row_index - 1,
                    "hypothesis_index": column_index,
                    "reference_char": normalized_reference[row_index - 1],
                    "hypothesis_char": "",
                }
            )
            row_index -= 1
        else:
            operations.append(
                {
                    "operation": "insertion",
                    "reference_index": row_index,
                    "hypothesis_index": column_index - 1,
                    "reference_char": "",
                    "hypothesis_char": normalized_hypothesis[column_index - 1],
                }
            )
            column_index -= 1
    operations.reverse()
    for operation in operations:
        reference_index = int(operation["reference_index"])
        context_start = max(0, reference_index - 12)
        context_end = min(len(normalized_reference), reference_index + 13)
        operation["reference_context"] = normalized_reference[context_start:context_end]
    return operations
