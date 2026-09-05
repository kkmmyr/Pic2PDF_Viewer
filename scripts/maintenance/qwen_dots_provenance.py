"""Runtime manifests collected by the processes in composite OCR runs."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _source_manifest(paths: Iterable[Path]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for path in paths:
        resolved = path.resolve()
        if not resolved.is_file():
            continue
        sources.append(
            {
                "name": resolved.name,
                "sha256": _sha256(resolved),
                "size": resolved.stat().st_size,
            }
        )
    return sources


def _package_versions(names: Iterable[str]) -> tuple[dict[str, str], list[str]]:
    installed: dict[str, str] = {}
    unavailable: list[str] = []
    for name in names:
        try:
            installed[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            unavailable.append(name)
    return installed, unavailable


def _device_manifest() -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        import torch  # pyright: ignore[reportMissingImports]

        result["torch"] = {
            "cuda_available": bool(torch.cuda.is_available()),
            "cuda_version": torch.version.cuda,
            "mps_available": bool(
                hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
            ),
        }
        if torch.cuda.is_available():
            result["torch"]["cuda_device_name"] = torch.cuda.get_device_name(0)
    except Exception as exc:
        result["torch_probe_error"] = type(exc).__name__
    try:
        import mlx.core as mx  # pyright: ignore[reportMissingImports]

        result["mlx"] = {"default_device": str(mx.default_device())}
    except Exception as exc:
        result["mlx_probe_error"] = type(exc).__name__
    return result


def collect_process_runtime_manifest(
    *,
    engine: str,
    model_revision: str,
    package_names: Iterable[str],
    source_paths: Iterable[Path],
) -> dict[str, Any]:
    """Record only observations made by this process, before inference begins."""
    revision = model_revision.strip()
    if not revision:
        raise ValueError("runtime manifest requires a fixed model revision")
    packages, unavailable_packages = _package_versions(package_names)
    sources = _source_manifest(source_paths)
    source_sha256 = hashlib.sha256(
        repr([(source["name"], source["sha256"]) for source in sources]).encode()
    ).hexdigest()
    return {
        "schema_version": 1,
        "engine": engine,
        "model_revision": revision,
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "package_versions": packages,
        "unavailable_packages": unavailable_packages,
        "device": _device_manifest(),
        "sources": sources,
        "source_sha256": source_sha256,
    }


def collect_qwen_runtime_manifest(
    model_revision: str, script_path: Path
) -> dict[str, Any]:
    return collect_process_runtime_manifest(
        engine="qwen3.5-ocr-jp-2b",
        model_revision=model_revision,
        package_names=("transformers", "torch", "Pillow"),
        source_paths=(script_path, Path(__file__)),
    )


def collect_dots_runtime_manifest(
    model_revision: str, script_path: Path
) -> dict[str, Any]:
    return collect_process_runtime_manifest(
        engine="dots.mocr",
        model_revision=model_revision,
        package_names=("mlx", "mlx-vlm", "Pillow"),
        source_paths=(script_path, Path(__file__)),
    )


def prediction_checkpoint_contract(config: Any, fingerprint: str) -> dict[str, Any]:
    fields = (
        "model_revision",
        "engine_version",
        "prompt_id",
        "seed",
        "max_tokens",
        "temperature",
        "top_p",
        "response_mode",
    )
    contract = {field: getattr(config, field) for field in fields}
    contract["model_fingerprint"] = fingerprint
    contract["prompt_sha256"] = hashlib.sha256(config.prompt.encode()).hexdigest()
    if config.runtime_manifest is not None:
        contract["runtime_manifest"] = config.runtime_manifest
    return contract


def dots_prediction_record(
    *,
    config: Any,
    page: Any,
    response: str,
    elapsed: float,
    fingerprint: str,
    prompt_sha256: str,
    extract_prediction: Any,
) -> dict[str, Any]:
    if not isinstance(response, str) or not response.strip():
        raise ValueError(f"dots.mocr prediction id {page.record_id} is empty")
    candidate_error: str | None = None
    try:
        prediction, layout_cell_count = extract_prediction(
            response,
            response_mode=config.response_mode,
            allow_empty_prediction=config.allow_empty_prediction,
        )
    except ValueError as exc:
        if not config.allow_empty_prediction:
            raise
        prediction = ""
        layout_cell_count = None
        candidate_error = str(exc)
    record = {
        "id": page.record_id,
        "pred": prediction,
        "input_sha256": page.image_sha256,
        "image_relpath": page.image_relpath,
        "model_revision": config.model_revision,
        "model_fingerprint": fingerprint,
        "engine_version": config.engine_version,
        "prompt_id": config.prompt_id,
        "prompt_sha256": prompt_sha256,
        "seed": config.seed,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "top_p": config.top_p,
        "response_mode": config.response_mode,
        "elapsed_seconds": elapsed,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    if config.runtime_manifest is not None:
        record["runtime_manifest"] = config.runtime_manifest
    if config.response_mode == "layout_json":
        record["raw_response"] = response
    if layout_cell_count is not None:
        record["layout_cell_count"] = layout_cell_count
        if not prediction.strip():
            record["image_only"] = True
    if candidate_error is not None:
        record["candidate_error"] = candidate_error
    return record


def attach_runtime_manifest(
    record: dict[str, Any], manifest: dict[str, Any] | None
) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise ValueError("prediction runtime manifest is required")
    record["runtime_manifest"] = manifest
    return record


def qwen_prediction_record(
    *,
    config: Any,
    page: Any,
    response: str,
    elapsed: float,
    fingerprint: str,
    prompt_sha256: str,
    prediction: str,
    block_count: int,
    html_truncated: bool,
    markup_tags: tuple[str, ...],
    bbox_order_suspicious: bool,
    suspicious_repetition: bool,
    html_protocol_version: str,
    generation_mode: str,
    candidate_error: str | None,
) -> dict[str, Any]:
    record = {
        "id": page.record_id,
        "pred": prediction,
        "raw_response": response,
        "raw_response_sha256": hashlib.sha256(response.encode()).hexdigest(),
        "layout_block_count": block_count,
        "html_truncated": html_truncated,
        "fallback_markup_tags": markup_tags,
        "suspicious_vertical_bbox_order": bbox_order_suspicious,
        "suspicious_repetition": suspicious_repetition,
        "input_sha256": page.image_sha256,
        "image_relpath": page.image_relpath,
        "model_revision": config.model_revision,
        "model_fingerprint": fingerprint,
        "engine_version": config.engine_version,
        "prompt_id": config.prompt_id,
        "prompt_sha256": prompt_sha256,
        "seed": config.seed,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "top_p": config.top_p,
        "response_mode": config.response_mode,
        "html_protocol_version": html_protocol_version,
        "generation_mode": generation_mode,
        "elapsed_seconds": elapsed,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    if candidate_error is not None:
        record["candidate_error"] = candidate_error
    return record


def prediction_provenance(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field: record.get(field)
        for field in (
            "model_revision",
            "model_fingerprint",
            "engine_version",
            "prompt_id",
            "prompt_sha256",
            "seed",
            "max_tokens",
            "temperature",
            "top_p",
            "response_mode",
            "generated_at",
            "elapsed_seconds",
            "candidate_error",
            "image_only",
            "html_truncated",
            "suspicious_repetition",
            "fallback_markup_tags",
            "suspicious_vertical_bbox_order",
        )
    }


def selected_prediction_record(
    *,
    record_id: str,
    qwen_record: Mapping[str, Any],
    dots_record: Mapping[str, Any],
    qwen_text: str,
    dots_text: str,
    use_fallback: bool,
    reason: str,
) -> dict[str, Any]:
    chosen = dots_record if use_fallback else qwen_record
    return {
        "id": record_id,
        "pred": dots_text if use_fallback else qwen_text,
        "primary_text": qwen_text,
        "external_text": dots_text,
        "primary_raw_output": qwen_record["raw_response"],
        "external_raw_output": dots_record.get("raw_response", ""),
        "primary_provenance": prediction_provenance(qwen_record),
        "external_provenance": prediction_provenance(dots_record),
        "primary_runtime_manifest": qwen_record["runtime_manifest"],
        "external_runtime_manifest": dots_record["runtime_manifest"],
        "input_sha256": qwen_record["input_sha256"],
        "selected_engine": "dots.mocr" if use_fallback else "qwen3.5-ocr-jp-2b",
        "selection_reason": reason,
        "selected_model_revision": chosen["model_revision"],
        "selected_model_fingerprint": chosen["model_fingerprint"],
        "selected_prompt_id": chosen["prompt_id"],
        "qwen_model_revision": qwen_record["model_revision"],
        "qwen_model_fingerprint": qwen_record["model_fingerprint"],
        "dots_model_revision": dots_record["model_revision"],
        "dots_model_fingerprint": dots_record["model_fingerprint"],
    }


def inference_manifest_signature(record: Mapping[str, Any], *, source: str) -> str:
    manifest = record.get("runtime_manifest")
    if (
        not isinstance(manifest, dict)
        or type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != 1
    ):
        raise ValueError(f"{source} id {record.get('id')} has no runtime manifest")
    if manifest.get("model_revision") != record["model_revision"]:
        raise ValueError(
            f"{source} id {record.get('id')} runtime manifest model revision mismatch"
        )
    expected_engine = "qwen3.5-ocr-jp-2b" if source == "qwen" else "dots.mocr"
    if manifest.get("engine") != expected_engine:
        raise ValueError(
            f"{source} id {record.get('id')} runtime manifest engine mismatch"
        )
    return json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
