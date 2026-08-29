"""Qwen3.5 OCR checkpoint fields that extend the shared dots contract."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any


def validate_qwen_checkpoint(
    checkpoint: Mapping[str, Mapping[str, Any]],
    *,
    html_protocol_version: str,
    generation_mode: str,
) -> None:
    expected = {
        "html_protocol_version": html_protocol_version,
        "generation_mode": generation_mode,
    }
    for record_id, record in checkpoint.items():
        for field, value in expected.items():
            if record.get(field) != value:
                raise ValueError(f"checkpoint id {record_id} {field} mismatch")
        raw_response = record.get("raw_response")
        if not isinstance(raw_response, str) or not raw_response.strip():
            raise ValueError(f"checkpoint id {record_id} has no raw_response")
        if (
            record.get("raw_response_sha256")
            != hashlib.sha256(raw_response.encode()).hexdigest()
        ):
            raise ValueError(f"checkpoint id {record_id} raw_response_sha256 mismatch")
