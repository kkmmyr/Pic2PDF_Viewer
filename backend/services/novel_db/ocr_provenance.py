"""Deterministic OCR runtime and candidate provenance manifests."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

_UNVERSIONED = {"", "unversioned", "unknown", "latest"}
_PACKAGE_NAMES = ("yomitoku", "torch", "torchvision", "numpy", "opencv-python", "Pillow")


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_model_revision(model_revision: str) -> str:
    revision = model_revision.strip()
    if revision.casefold() in _UNVERSIONED:
        raise ValueError("OCR model revision must be fixed; blank/unversioned/unknown/latest is not allowed")
    return revision


def _sha256_file(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _file_manifest(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "size": stat.st_size,
        "sha256": _sha256_file(path),
    }


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in _PACKAGE_NAMES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
    return versions


def _device_manifest() -> dict[str, Any]:
    result: dict[str, Any] = {"backend": "cpu", "name": platform.processor() or platform.machine()}
    try:
        import torch  # type: ignore[import-not-found]

        result["torch_cuda_version"] = torch.version.cuda
        result["cuda_available"] = bool(torch.cuda.is_available())
        result["mps_available"] = bool(hasattr(torch.backends, "mps") and torch.backends.mps.is_available())
        if result["cuda_available"]:
            result.update(backend="cuda", name=torch.cuda.get_device_name(0))
        elif result["mps_available"]:
            result.update(backend="mps", name="Apple Metal Performance Shaders")
    except Exception as exc:
        result["probe_error"] = type(exc).__name__
    return result


def _git_manifest(repo_root: Path) -> dict[str, Any]:
    def run(*args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return completed.stdout.strip()

    try:
        return {
            "commit": run("rev-parse", "HEAD"),
            "dirty": bool(run("status", "--porcelain", "--untracked-files=no")),
        }
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def collect_runtime_manifest(engine: str, model_revision: str) -> dict[str, Any]:
    """Collect provenance inside the process that actually performs OCR."""
    revision = validate_model_revision(model_revision)
    module_dir = Path(__file__).resolve().parent
    repo_root = module_dir.parents[2]
    source_names = (
        "ocr_worker.py",
        "ocr_worker_protocol.py",
        "ocr_worker_engines.py",
        "ocr_worker_session.py",
        "surya_runtime.py",
        "yomitoku_runtime.py",
    )
    sources = [_file_manifest(module_dir / name) for name in source_names if (module_dir / name).is_file()]
    wrapper_path = Path(os.environ.get("OCR_PATH", "")) / "ocr_engine.py"
    wrapper = _file_manifest(wrapper_path) if wrapper_path.is_file() else None
    model_files = []
    for env_name in ("SURYA_MODEL_PATH", "SURYA_MMPROJ_PATH"):
        value = os.environ.get(env_name)
        if value and Path(value).is_file():
            model_files.append(_file_manifest(Path(value)))
    pipeline_digest = hashlib.sha256(canonical_json({"sources": sources, "wrapper": wrapper}).encode()).hexdigest()
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "engine": engine.casefold(),
        "model_revision": revision,
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "package_versions": _package_versions(),
        "device": _device_manifest(),
        "sources": sources,
        "wrapper": wrapper,
        "model_files": model_files,
        "pipeline_sha256": pipeline_digest,
        "git": _git_manifest(repo_root),
        "process": {"executable_name": Path(sys.executable).name},
    }
    return manifest


def candidate_manifest(
    *,
    primary_text: str,
    primary_raw_output: str,
    primary_state: str,
    primary_block_count: int,
    primary_quality_flags: list[str],
    primary_attempt_count: int,
    external_text: str | None,
    external_raw_output: str | None,
    external_state: str | None,
    external_block_count: int | None,
    external_quality_flags: list[str] | None,
    external_attempt_count: int | None,
) -> dict[str, Any]:
    def entry(
        text: str,
        raw_output: str,
        state: str,
        block_count: int,
        quality_flags: list[str],
        attempt_count: int,
    ) -> dict[str, Any]:
        return {
            "state": state,
            "char_count": len(text),
            "block_count": block_count,
            "quality_flags": quality_flags,
            "attempt_count": attempt_count,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "raw_output_sha256": hashlib.sha256(raw_output.encode("utf-8")).hexdigest(),
        }

    result: dict[str, Any] = {
        "schema_version": 1,
        "primary": entry(
            primary_text,
            primary_raw_output,
            primary_state,
            primary_block_count,
            primary_quality_flags,
            primary_attempt_count,
        ),
        "external": None,
    }
    if external_text is not None:
        result["external"] = entry(
            external_text,
            external_raw_output or "",
            external_state or "unknown",
            external_block_count or 0,
            external_quality_flags or [],
            external_attempt_count or 0,
        )
    return result
