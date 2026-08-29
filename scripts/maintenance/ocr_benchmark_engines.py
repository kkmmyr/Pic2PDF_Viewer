"""OCR benchmark corpus I/O and engine adapters."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import urlopen


def _get_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=120) as response:  # noqa: S310 - operator supplied API URL
        return json.load(response)


def _run_qa_candidate(
    entries: list[dict[str, Any]], api_base: str, field: str
) -> dict[int, str]:
    """Load a frozen run/page candidate without using the corrected published text."""
    if field not in {"primary_text", "external_text"}:
        raise ValueError(f"unsupported QA candidate field: {field}")
    run_details = {
        run_id: _get_json(f"{api_base.rstrip('/')}/api/ocr/qa/runs/{run_id}")
        for run_id in sorted({int(entry["run_id"]) for entry in entries})
    }
    pages_by_run = {
        run_id: {int(page["page_no"]): page for page in detail["pages"]}
        for run_id, detail in run_details.items()
    }
    hypotheses: dict[int, str] = {}
    for entry in entries:
        entry_id = int(entry["id"])
        run_id = int(entry["run_id"])
        page_no = int(entry["page_no"])
        page = pages_by_run[run_id].get(page_no)
        if page is None:
            raise ValueError(f"OCR QA page not found: run={run_id}, page={page_no}")
        hypotheses[entry_id] = str(page.get(field) or "")
    return hypotheses


def _download_images(
    entries: list[dict[str, Any]], api_base: str, images_dir: Path
) -> dict[int, Path]:
    image_paths: dict[int, Path] = {}
    for entry in entries:
        entry_id = int(entry["id"])
        image_url = urljoin(
            f"{api_base.rstrip('/')}/", str(entry["image_url"]).lstrip("/")
        )
        with urlopen(image_url, timeout=30) as response:  # noqa: S310 - same trusted API
            image_bytes = response.read()
        actual_sha256 = hashlib.sha256(image_bytes).hexdigest()
        expected_sha256 = str(entry["image_sha256"])
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"image SHA-256 mismatch for entry {entry_id}: "
                f"expected {expected_sha256}, got {actual_sha256}"
            )
        image_path = images_dir / f"{entry_id:04d}.png"
        image_path.write_bytes(image_bytes)
        image_paths[entry_id] = image_path
    return image_paths


def _run_tesseract(
    entries: list[dict[str, Any]],
    image_paths: dict[int, Path],
    executable: Path,
    tessdata_dir: Path,
) -> dict[int, str]:
    hypotheses: dict[int, str] = {}
    for entry in entries:
        entry_id = int(entry["id"])
        command = [
            str(executable),
            str(image_paths[entry_id]),
            "stdout",
            "--tessdata-dir",
            str(tessdata_dir),
            "-l",
            "jpn_vert",
            "--psm",
            "5",
        ]
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        hypotheses[entry_id] = result.stdout
    return hypotheses


def _run_yomitoku(
    entries: list[dict[str, Any]],
    image_paths: dict[int, Path],
    ocr_python: Path,
    ocr_path: Path,
    repo_root: Path,
    work_dir: Path,
    yomitoku_device: str = "auto",
) -> dict[int, str]:
    manifest_path = work_dir / "yomitoku-manifest.json"
    tasks = [
        {
            "book_name": str(entry["book_name"]),
            "page_no": int(entry["id"]),
            "image_path": str(image_paths[int(entry["id"])]),
        }
        for entry in entries
    ]
    manifest_path.write_text(
        json.dumps({"tasks": tasks}, ensure_ascii=False),
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "OCR_ENGINE": "yomitoku",
        "OCR_PATH": str(ocr_path),
        "OCR_YOMITOKU_DEVICE": yomitoku_device,
    }
    result = subprocess.run(
        [
            str(ocr_python),
            str(repo_root / "backend" / "services" / "novel_db" / "ocr_worker.py"),
            "--manifest",
            str(manifest_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    hypotheses: dict[int, str] = {}
    for line in result.stdout.splitlines():
        event = json.loads(line)
        if event.get("event") != "page":
            continue
        page = event["page"]
        entry_id = int(page["page_no"])
        if page["state"] != "passed":
            raise RuntimeError(
                f"yomitoku failed for entry {entry_id}: {page['error_message']}"
            )
        hypotheses[entry_id] = str(page["full_text"])
    missing = sorted(set(image_paths) - set(hypotheses))
    if missing:
        raise RuntimeError(f"yomitoku returned no result for entries: {missing}")
    return hypotheses


def _is_truthy(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.lower() == "true")


def _flatten_ndlocr_contents(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        flattened: list[dict[str, Any]] = []
        for item in value:
            flattened.extend(_flatten_ndlocr_contents(item))
        return flattened
    return []


def parse_ndlocr_payload(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Normalize NDLOCR-Lite lines and preserve bbox data for later column QA."""
    segments: list[dict[str, Any]] = []
    for line in _flatten_ndlocr_contents(payload.get("contents", [])):
        text = str(line.get("text", "")).strip()
        if not text or not _is_truthy(line.get("isTextline", True)):
            continue
        bbox = line.get("boundingBox")
        if not isinstance(bbox, list) or not bbox:
            continue
        points = [
            point
            for point in bbox
            if isinstance(point, list)
            and len(point) >= 2
            and all(isinstance(coordinate, (int, float)) for coordinate in point[:2])
        ]
        if not points:
            continue
        center_x = sum(float(point[0]) for point in points) / len(points)
        center_y = sum(float(point[1]) for point in points) / len(points)
        is_vertical = _is_truthy(line.get("isVertical"))
        segments.append(
            {
                "text": text,
                "bbox": bbox,
                "confidence": line.get("confidence"),
                "is_vertical": is_vertical,
                "center_x": center_x,
                "center_y": center_y,
            }
        )

    vertical_count = sum(segment["is_vertical"] for segment in segments)
    predominantly_vertical = vertical_count >= max(1, len(segments) - vertical_count)
    if predominantly_vertical:
        segments.sort(key=lambda segment: (-segment["center_x"], segment["center_y"]))
    else:
        segments.sort(key=lambda segment: (segment["center_y"], segment["center_x"]))
    for segment in segments:
        segment.pop("center_x")
        segment.pop("center_y")
    return "\n".join(str(segment["text"]) for segment in segments), segments


def _run_ndlocr(
    entries: list[dict[str, Any]],
    image_paths: dict[int, Path],
    ndlocr_python: Path,
    ndlocr_script: Path,
    work_dir: Path,
    rec_weights: Path | None = None,
) -> tuple[dict[int, str], dict[int, list[dict[str, Any]]]]:
    hypotheses: dict[int, str] = {}
    segments_by_entry: dict[int, list[dict[str, Any]]] = {}
    output_dir = work_dir / "ndlocr-batch"
    output_dir.mkdir()
    command = [
        str(ndlocr_python),
        str(ndlocr_script),
        "--sourcedir",
        str(work_dir),
        "--output",
        str(output_dir),
        "--json-only",
    ]
    if rec_weights is not None:
        command.extend(["--rec-weights", str(rec_weights)])
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=ndlocr_script.parent.parent,
    )
    for entry in entries:
        entry_id = int(entry["id"])
        json_path = output_dir / f"{image_paths[entry_id].stem}.json"
        if not json_path.is_file():
            raise RuntimeError(
                f"NDLOCR-Lite produced no JSON file for entry "
                f"{entry_id}: stdout={result.stdout!r}, stderr={result.stderr!r}"
            )
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        hypothesis, segments = parse_ndlocr_payload(payload)
        hypotheses[entry_id] = hypothesis
        segments_by_entry[entry_id] = segments
    return hypotheses, segments_by_entry


def _load_hypotheses_from_report(
    entries: list[dict[str, Any]], source_report_path: Path
) -> dict[int, str]:
    source_report = json.loads(source_report_path.read_text(encoding="utf-8"))
    source_pages = {int(page["entry_id"]): page for page in source_report["pages"]}
    hypotheses: dict[int, str] = {}
    for entry in entries:
        entry_id = int(entry["id"])
        page = source_pages.get(entry_id)
        if page is None:
            raise ValueError(f"source report has no hypothesis for entry {entry_id}")
        if str(page["image_sha256"]) != str(entry["image_sha256"]):
            raise ValueError(
                f"source report image SHA-256 mismatch for entry {entry_id}"
            )
        hypotheses[entry_id] = str(page["hypothesis"])
    return hypotheses
