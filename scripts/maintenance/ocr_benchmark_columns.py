"""Paddle and Surya column-oriented OCR benchmark adapters."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _run_paddle(
    entries: list[dict[str, Any]],
    image_paths: dict[int, Path],
    paddle_python: Path,
    paddle_worker: Path,
    paddle_device: str,
    paddle_det_limit_side_len: int,
    work_dir: Path,
) -> tuple[dict[int, str], dict[int, list[dict[str, Any]]]]:
    manifest_path = work_dir / "paddle-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "entry_id": int(entry["id"]),
                        "image_path": str(image_paths[int(entry["id"])]),
                    }
                    for entry in entries
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            str(paddle_python),
            str(paddle_worker),
            "--manifest",
            str(manifest_path),
            "--device",
            paddle_device,
            "--det-limit-side-len",
            str(paddle_det_limit_side_len),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"PaddleOCR worker failed with exit code {result.returncode}: "
            f"stdout={result.stdout!r}, stderr={result.stderr!r}"
        )
    hypotheses: dict[int, str] = {}
    segments_by_entry: dict[int, list[dict[str, Any]]] = {}
    for line in result.stdout.splitlines():
        if not line.startswith("{"):
            continue
        event = json.loads(line)
        entry_id = int(event["entry_id"])
        hypotheses[entry_id] = str(event["text"])
        segments_by_entry[entry_id] = list(event["segments"])
    missing = sorted(set(image_paths) - set(hypotheses))
    if missing:
        raise RuntimeError(
            f"PaddleOCR returned no result for entries {missing}: "
            f"stderr={result.stderr!r}"
        )
    return hypotheses, segments_by_entry


def _run_paddle_columns(
    entries: list[dict[str, Any]],
    image_paths: dict[int, Path],
    segment_report_path: Path,
    paddle_python: Path,
    paddle_column_worker: Path,
    paddle_device: str,
    paddle_column_margin: int,
    paddle_column_scale: float,
    work_dir: Path,
) -> tuple[dict[int, str], dict[int, list[dict[str, Any]]]]:
    segment_report = json.loads(segment_report_path.read_text(encoding="utf-8"))
    source_pages = {int(page["entry_id"]): page for page in segment_report["pages"]}
    tasks = []
    for entry in entries:
        entry_id = int(entry["id"])
        source_page = source_pages.get(entry_id)
        if source_page is None or "segments" not in source_page:
            raise ValueError(f"segment report has no bbox data for entry {entry_id}")
        if str(source_page["image_sha256"]) != str(entry["image_sha256"]):
            raise ValueError(
                f"segment report image SHA-256 mismatch for entry {entry_id}"
            )
        tasks.append(
            {
                "entry_id": entry_id,
                "image_path": str(image_paths[entry_id]),
                "segments": source_page["segments"],
            }
        )
    manifest_path = work_dir / "paddle-column-manifest.json"
    manifest_path.write_text(
        json.dumps({"tasks": tasks}, ensure_ascii=False), encoding="utf-8"
    )
    result = subprocess.run(
        [
            str(paddle_python),
            str(paddle_column_worker),
            "--manifest",
            str(manifest_path),
            "--device",
            paddle_device,
            "--margin",
            str(paddle_column_margin),
            "--scale",
            str(paddle_column_scale),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"PP-OCRv5 column worker failed with exit code {result.returncode}: "
            f"stdout={result.stdout!r}, stderr={result.stderr!r}"
        )
    hypotheses: dict[int, str] = {}
    segments_by_entry: dict[int, list[dict[str, Any]]] = {}
    for line in result.stdout.splitlines():
        if not line.startswith("{"):
            continue
        event = json.loads(line)
        entry_id = int(event["entry_id"])
        hypotheses[entry_id] = str(event["text"])
        segments_by_entry[entry_id] = list(event["segments"])
    missing = sorted(set(image_paths) - set(hypotheses))
    if missing:
        raise RuntimeError(
            f"PP-OCRv5 column worker returned no result for entries {missing}: "
            f"stderr={result.stderr!r}"
        )
    return hypotheses, segments_by_entry


def _run_surya_columns(
    entries: list[dict[str, Any]],
    image_paths: dict[int, Path],
    segment_report_path: Path,
    surya_worker: Path,
    surya_server: Path,
    surya_model_path: Path,
    surya_mmproj_path: Path,
    surya_group_size: int,
    surya_column_margin: int,
    work_dir: Path,
) -> tuple[dict[int, str], dict[int, list[dict[str, Any]]]]:
    segment_report = json.loads(segment_report_path.read_text(encoding="utf-8"))
    source_pages = {int(page["entry_id"]): page for page in segment_report["pages"]}
    tasks = []
    for entry in entries:
        entry_id = int(entry["id"])
        source_page = source_pages.get(entry_id)
        if source_page is None or "segments" not in source_page:
            raise ValueError(f"segment report has no bbox data for entry {entry_id}")
        if str(source_page["image_sha256"]) != str(entry["image_sha256"]):
            raise ValueError(
                f"segment report image SHA-256 mismatch for entry {entry_id}"
            )
        tasks.append(
            {
                "entry_id": entry_id,
                "image_path": str(image_paths[entry_id]),
                "segments": source_page["segments"],
            }
        )
    manifest_path = work_dir / "surya-column-manifest.json"
    manifest_path.write_text(
        json.dumps({"tasks": tasks}, ensure_ascii=False), encoding="utf-8"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(surya_worker),
            "--manifest",
            str(manifest_path),
            "--server",
            str(surya_server),
            "--model-path",
            str(surya_model_path),
            "--mmproj-path",
            str(surya_mmproj_path),
            "--group-size",
            str(surya_group_size),
            "--margin",
            str(surya_column_margin),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=Path(__file__).resolve().parents[2],
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Surya column worker failed with exit code {result.returncode}: "
            f"stdout={result.stdout!r}, stderr={result.stderr!r}"
        )
    hypotheses: dict[int, str] = {}
    segments_by_entry: dict[int, list[dict[str, Any]]] = {}
    for line in result.stdout.splitlines():
        if not line.startswith("{"):
            continue
        event = json.loads(line)
        entry_id = int(event["entry_id"])
        hypotheses[entry_id] = str(event["text"])
        segments_by_entry[entry_id] = list(event["segments"])
    missing = sorted(set(image_paths) - set(hypotheses))
    if missing:
        raise RuntimeError(
            f"Surya column worker returned no result for entries {missing}: "
            f"stderr={result.stderr!r}"
        )
    return hypotheses, segments_by_entry
