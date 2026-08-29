"""Codex端末間連携の入力制約と共通例外。"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
MAX_BODY_CHARS = 65_536
MAX_SUBJECT_CHARS = 256
MAX_RESOLUTION_CHARS = 8_192
MAX_IDEMPOTENCY_KEY_CHARS = 256
MAX_REFS_BYTES = 16_384
MAX_CONTEXT_BYTES = 262_144


class CoordinationValidationError(ValueError):
    """入力値が連携契約を満たさない。"""


class CoordinationNotFoundError(LookupError):
    """対象messageまたはtopicが存在しない。"""


class CoordinationConflictError(RuntimeError):
    """冪等キーまたは状態遷移が既存状態と競合した。"""


class CoordinationAuthorizationError(PermissionError):
    """agentが対象messageまたはtopicの参加者ではない。"""


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def validate_identifier(value: str, name: str) -> str:
    if not IDENTIFIER_RE.fullmatch(value):
        raise CoordinationValidationError(f"{name} must match {IDENTIFIER_RE.pattern}")
    return value


def validate_text(value: str, name: str, limit: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise CoordinationValidationError(f"{name} must not be empty")
    if len(normalized) > limit:
        raise CoordinationValidationError(f"{name} exceeds {limit} characters")
    return normalized


def canonical_object(
    value: dict[str, Any] | None,
    *,
    name: str,
    max_bytes: int,
) -> tuple[dict[str, Any], str]:
    normalized = value or {}
    try:
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise CoordinationValidationError(f"{name} must contain JSON values") from exc
    if len(encoded.encode("utf-8")) > max_bytes:
        raise CoordinationValidationError(f"{name} exceeds {max_bytes} bytes")
    return normalized, encoded
