"""Benchmark OCR engines against the verified ground-truth corpus.

Examples:
    uv run python scripts/maintenance/benchmark_ocr_ground_truth.py current
    uv run python scripts/maintenance/benchmark_ocr_ground_truth.py tesseract \
        --tesseract "C:/Program Files/Tesseract-OCR/tesseract.exe" \
        --tessdata-dir "C:/path/to/tessdata-best"
    uv run python scripts/maintenance/benchmark_ocr_ground_truth.py yomitoku \
        --ocr-python "D:/61.tool/common/ocr/venv/Scripts/python.exe" \
        --ocr-path "D:/61.tool/common/ocr"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import urlopen

PAGE_TYPE_ORDER = ("narrative", "toc", "illustration", "colophon_or_ad", "unknown")


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


def character_error_rate(reference: str, hypothesis: str) -> tuple[int, int, float | None]:
    normalized_reference = re.sub(r"\s+", "", reference)
    normalized_hypothesis = re.sub(r"\s+", "", hypothesis)
    distance = _edit_distance(normalized_reference, normalized_hypothesis)
    reference_chars = len(normalized_reference)
    return distance, reference_chars, distance / reference_chars if reference_chars else None


def _get_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=30) as response:  # noqa: S310 - operator supplied API URL
        return json.load(response)


def _download_images(
    entries: list[dict[str, Any]], api_base: str, images_dir: Path
) -> dict[int, Path]:
    image_paths: dict[int, Path] = {}
    for entry in entries:
        entry_id = int(entry["id"])
        image_url = urljoin(f"{api_base.rstrip('/')}/", str(entry["image_url"]).lstrip("/"))
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
            raise RuntimeError(f"yomitoku failed for entry {entry_id}: {page['error_message']}")
        hypotheses[entry_id] = str(page["full_text"])
    missing = sorted(set(image_paths) - set(hypotheses))
    if missing:
        raise RuntimeError(f"yomitoku returned no result for entries: {missing}")
    return hypotheses


def summarize(
    entries: list[dict[str, Any]], hypotheses: dict[int, str], engine: str
) -> dict[str, Any]:
    totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {"page_count": 0, "total_edit_distance": 0, "total_reference_chars": 0}
    )
    pages = []
    for entry in entries:
        entry_id = int(entry["id"])
        hypothesis = hypotheses[entry_id]
        distance, reference_chars, cer = character_error_rate(
            str(entry["reference_text"]), hypothesis
        )
        page_type = str(entry["page_type"])
        for group in ("overall", page_type):
            totals[group]["page_count"] += 1
            totals[group]["total_edit_distance"] += distance
            totals[group]["total_reference_chars"] += reference_chars
        pages.append(
            {
                "entry_id": entry_id,
                "run_id": int(entry["run_id"]),
                "page_no": int(entry["page_no"]),
                "page_type": page_type,
                "image_sha256": str(entry["image_sha256"]),
                "edit_distance": distance,
                "reference_chars": reference_chars,
                "cer": cer,
                "hypothesis": hypothesis,
            }
        )

    metrics = []
    for group in ("overall", *PAGE_TYPE_ORDER):
        values = totals[group]
        if values["page_count"] == 0:
            continue
        reference_chars = values["total_reference_chars"]
        metrics.append(
            {
                "group": group,
                **values,
                "aggregate_cer": (
                    values["total_edit_distance"] / reference_chars
                    if reference_chars
                    else None
                ),
            }
        )
    return {
        "engine": engine,
        "generated_at": datetime.now(UTC).isoformat(),
        "metrics": metrics,
        "pages": pages,
    }


def _print_summary(report: dict[str, Any]) -> None:
    print(f"engine: {report['engine']}")
    for metric in report["metrics"]:
        cer = metric["aggregate_cer"]
        cer_text = "—" if cer is None else f"{cer * 100:.2f}%"
        print(
            f"{metric['group']}: pages={metric['page_count']}, "
            f"chars={metric['total_reference_chars']}, CER={cer_text}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("engine", choices=("current", "tesseract", "yomitoku"))
    parser.add_argument("--api-base", default="http://medaroserver:8090")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tesseract", type=Path)
    parser.add_argument("--tessdata-dir", type=Path)
    parser.add_argument("--ocr-python", type=Path)
    parser.add_argument("--ocr-path", type=Path)
    args = parser.parse_args()

    corpus = _get_json(f"{args.api_base.rstrip('/')}/api/ocr/ground-truth")
    entries = [entry for entry in corpus["entries"] if entry["state"] == "verified"]
    if not entries:
        raise RuntimeError("verified ground-truth corpus is empty")

    repo_root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="pic2pdf-ocr-benchmark-") as temp_dir:
        work_dir = Path(temp_dir)
        if args.engine == "current":
            hypotheses = {int(entry["id"]): str(entry["ocr_text"]) for entry in entries}
        else:
            image_paths = _download_images(entries, args.api_base, work_dir)
            if args.engine == "tesseract":
                if args.tesseract is None or args.tessdata_dir is None:
                    parser.error("tesseract requires --tesseract and --tessdata-dir")
                hypotheses = _run_tesseract(
                    entries, image_paths, args.tesseract, args.tessdata_dir
                )
            else:
                if args.ocr_python is None or args.ocr_path is None:
                    parser.error("yomitoku requires --ocr-python and --ocr-path")
                hypotheses = _run_yomitoku(
                    entries,
                    image_paths,
                    args.ocr_python,
                    args.ocr_path,
                    repo_root,
                    work_dir,
                )

    report = summarize(entries, hypotheses, args.engine)
    _print_summary(report)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
