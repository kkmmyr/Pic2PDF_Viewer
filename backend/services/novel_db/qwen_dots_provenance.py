"""Aggregate independently observed Qwen and dots runtime manifests."""

from __future__ import annotations

import json
from typing import Any

try:
    from .ocr_provenance import collect_runtime_manifest
except ImportError:
    from ocr_provenance import collect_runtime_manifest


def _signature(
    record: dict[str, Any],
    *,
    field: str,
    engine: str,
    model_revision: str,
) -> str:
    manifest = record.get(field)
    if (
        not isinstance(manifest, dict)
        or type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != 1
    ):
        raise ValueError(f"selected record {record.get('id')} has no {field}")
    if manifest.get("engine") != engine:
        raise ValueError(f"selected record {record.get('id')} {field} engine mismatch")
    if manifest.get("model_revision") != model_revision:
        raise ValueError(f"selected record {record.get('id')} {field} model revision mismatch")
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def composite_runtime_manifest(
    records: list[dict[str, Any]],
    *,
    qwen_model_revision: str,
    dots_model_revision: str,
    composite_model_revision: str,
) -> dict[str, Any]:
    if not records:
        raise ValueError("composite OCR selected output is empty")
    qwen = {
        _signature(
            record,
            field="primary_runtime_manifest",
            engine="qwen3.5-ocr-jp-2b",
            model_revision=qwen_model_revision,
        )
        for record in records
    }
    dots = {
        _signature(
            record,
            field="external_runtime_manifest",
            engine="dots.mocr",
            model_revision=dots_model_revision,
        )
        for record in records
    }
    if len(qwen) != 1:
        raise ValueError("selected Qwen records mix runtime manifests")
    if len(dots) != 1:
        raise ValueError("selected dots records mix runtime manifests")
    return {
        "schema_version": 1,
        "engine": "qwen35_dots_review_v1",
        "model_revision": composite_model_revision,
        "inference_processes": {
            "qwen": json.loads(next(iter(qwen))),
            "dots": json.loads(next(iter(dots))),
        },
        "adjudication_worker": collect_runtime_manifest(
            "qwen35_dots_review_v1",
            composite_model_revision,
        ),
    }
