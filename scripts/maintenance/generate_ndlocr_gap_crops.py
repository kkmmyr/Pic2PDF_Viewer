"""Generate diagnostic crops for vertical columns omitted by NDLOCR detection.

The command is deliberately read-only with respect to OCR QA and publication.
It only verifies source images, writes crop images, and emits a private manifest
for a later recognition/QA step.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any
from urllib.request import Request, urlopen

from PIL import Image


def _bbox_extents(segment: dict[str, Any]) -> tuple[float, float, float, float] | None:
    bbox = segment.get("bbox")
    if not isinstance(bbox, list):
        return None
    points = [
        point
        for point in bbox
        if isinstance(point, list)
        and len(point) >= 2
        and isinstance(point[0], (int, float))
        and isinstance(point[1], (int, float))
    ]
    if not points:
        return None
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _is_vertical(segment: dict[str, Any]) -> bool:
    value = segment.get("is_vertical")
    return value is True or (isinstance(value, str) and value.lower() == "true")


def infer_missing_columns(
    segments: Sequence[dict[str, Any]],
    *,
    min_gap_ratio: float,
    max_rightmost_header_chars: int,
    max_missing_per_gap: int = 3,
) -> list[dict[str, Any]]:
    """Infer missing vertical-column centers from unusually wide bbox gaps."""

    columns = []
    for segment in segments:
        if not _is_vertical(segment):
            continue
        extents = _bbox_extents(segment)
        if extents is None:
            continue
        left, top, right, bottom = extents
        columns.append(
            {
                "center_x": (left + right) / 2,
                "left": left,
                "top": top,
                "right": right,
                "bottom": bottom,
                "chars": len("".join(str(segment.get("text", "")).split())),
            }
        )
    columns.sort(key=lambda item: float(item["center_x"]), reverse=True)
    if len(columns) < 4:
        return []

    gaps = [
        float(columns[index]["center_x"]) - float(columns[index + 1]["center_x"])
        for index in range(len(columns) - 1)
    ]
    positive_gaps = [gap for gap in gaps if gap > 0]
    if len(positive_gaps) < 3:
        return []
    median_gap = float(median(positive_gaps))
    if median_gap <= 0:
        return []

    median_width = float(
        median(float(column["right"]) - float(column["left"]) for column in columns)
    )
    global_top = min(float(column["top"]) for column in columns)
    global_bottom = max(float(column["bottom"]) for column in columns)
    inferred: list[dict[str, Any]] = []
    for gap_index, gap in enumerate(gaps):
        if gap <= 0:
            continue
        if gap_index == 0 and int(columns[0]["chars"]) <= max_rightmost_header_chars:
            continue
        gap_ratio = gap / median_gap
        if gap_ratio < min_gap_ratio:
            continue
        missing_count = min(
            max_missing_per_gap,
            max(1, int(round(gap_ratio)) - 1),
        )
        step = gap / (missing_count + 1)
        right_center = float(columns[gap_index]["center_x"])
        for missing_index in range(missing_count):
            inferred.append(
                {
                    "gap_index": gap_index,
                    "missing_index": missing_index,
                    "missing_count": missing_count,
                    "center_x": right_center - step * (missing_index + 1),
                    "column_width": median_width,
                    "top": global_top,
                    "bottom": global_bottom,
                    "median_gap": median_gap,
                    "gap": gap,
                    "gap_ratio": gap_ratio,
                }
            )
    return inferred


def crop_inferred_column(
    image: Image.Image,
    inferred: dict[str, Any],
    *,
    margin: int,
    ink_threshold: int,
    dark_threshold: int,
    min_dark_pixels: int,
) -> tuple[Image.Image | None, dict[str, Any]]:
    """Crop and foreground-trim one inferred column, rejecting sparse artifacts."""

    center_x = float(inferred["center_x"])
    half_width = max(1.0, float(inferred["column_width"]) / 2)
    left = max(0, math.floor(center_x - half_width - margin))
    right = min(image.width, math.ceil(center_x + half_width + margin) + 1)
    top = max(0, math.floor(float(inferred["top"])) - margin)
    bottom = min(image.height, math.ceil(float(inferred["bottom"])) + margin + 1)
    if right <= left or bottom <= top:
        return None, {"reason": "invalid_bbox", "crop_bbox": [left, top, right, bottom]}

    band = image.crop((left, top, right, bottom)).convert("L")
    ink_mask = band.point(lambda value: 255 if value < ink_threshold else 0)
    ink_bbox = ink_mask.getbbox()
    if ink_bbox is None:
        return None, {"reason": "no_ink", "crop_bbox": [left, top, right, bottom]}

    ink_left, ink_top, ink_right, ink_bottom = ink_bbox
    trim_left = max(0, ink_left - margin)
    trim_top = max(0, ink_top - margin)
    trim_right = min(band.width, ink_right + margin)
    trim_bottom = min(band.height, ink_bottom + margin)
    trimmed = band.crop((trim_left, trim_top, trim_right, trim_bottom))
    dark_pixels = sum(trimmed.histogram()[:dark_threshold])
    source_bbox = [
        left + trim_left,
        top + trim_top,
        left + trim_right,
        top + trim_bottom,
    ]
    details = {
        "crop_bbox": source_bbox,
        "dark_pixels": dark_pixels,
        "width": trimmed.width,
        "height": trimmed.height,
    }
    if dark_pixels < min_dark_pixels:
        return None, {**details, "reason": "insufficient_dark_pixels"}
    return trimmed.convert("RGB"), {**details, "reason": None}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_missing_images(
    report: dict[str, Any], *, images_dir: Path, api_base: str
) -> int:
    """Download missing verified images without replacing existing files."""

    images_dir.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    for page in report.get("pages", []):
        entry_id = int(page["entry_id"])
        image_path = images_dir / f"{entry_id:04d}.png"
        if image_path.is_file():
            continue
        request = Request(
            f"{api_base.rstrip('/')}/api/ocr/ground-truth/{entry_id}/image",
            method="GET",
        )
        with urlopen(request, timeout=60) as response:  # noqa: S310 - operator API
            image_bytes = response.read()
        actual_sha = hashlib.sha256(image_bytes).hexdigest()
        expected_sha = str(page.get("image_sha256") or "")
        if expected_sha and actual_sha != expected_sha:
            raise ValueError(
                f"downloaded image SHA-256 mismatch for entry {entry_id}: "
                f"expected {expected_sha}, got {actual_sha}"
            )
        image_path.write_bytes(image_bytes)
        downloaded += 1
    return downloaded


def generate_manifest(
    report: dict[str, Any],
    *,
    images_dir: Path,
    crops_dir: Path,
    min_gap_ratio: float,
    max_rightmost_header_chars: int,
    max_missing_per_gap: int,
    margin: int,
    ink_threshold: int,
    dark_threshold: int,
    min_dark_pixels: int,
) -> dict[str, Any]:
    crops_dir.mkdir(parents=True, exist_ok=True)
    accepted = []
    rejected = []
    checked_pages = 0
    for page in report.get("pages", []):
        entry_id = int(page["entry_id"])
        source_path = images_dir / f"{entry_id:04d}.png"
        if not source_path.is_file():
            raise FileNotFoundError(f"source image not found: {source_path}")
        expected_sha = str(page.get("image_sha256") or "")
        actual_sha = _sha256(source_path)
        if expected_sha and actual_sha != expected_sha:
            raise ValueError(
                f"image SHA-256 mismatch for entry {entry_id}: "
                f"expected {expected_sha}, got {actual_sha}"
            )
        inferred_columns = infer_missing_columns(
            page.get("segments", []),
            min_gap_ratio=min_gap_ratio,
            max_rightmost_header_chars=max_rightmost_header_chars,
            max_missing_per_gap=max_missing_per_gap,
        )
        if not inferred_columns:
            continue
        checked_pages += 1
        with Image.open(source_path) as source_image:
            image = source_image.convert("RGB")
            for crop_index, inferred in enumerate(inferred_columns):
                crop, details = crop_inferred_column(
                    image,
                    inferred,
                    margin=margin,
                    ink_threshold=ink_threshold,
                    dark_threshold=dark_threshold,
                    min_dark_pixels=min_dark_pixels,
                )
                item = {
                    "entry_id": entry_id,
                    "run_id": int(page["run_id"]),
                    "page_no": int(page["page_no"]),
                    "image_sha256": actual_sha,
                    "source_image": str(source_path.resolve()),
                    "gap_index": int(inferred["gap_index"]),
                    "missing_index": int(inferred["missing_index"]),
                    "missing_count": int(inferred["missing_count"]),
                    "gap_ratio": float(inferred["gap_ratio"]),
                    **details,
                }
                if crop is None:
                    rejected.append(item)
                    continue
                crop_path = crops_dir / f"e{entry_id:04d}-g{crop_index:02d}.png"
                crop.save(crop_path, format="PNG")
                accepted.append({**item, "crop_path": str(crop_path.resolve())})

    return {
        "diagnostic_only": True,
        "publishes_ocr": False,
        "generated_at": datetime.now(UTC).isoformat(),
        "rule": {
            "min_gap_ratio": min_gap_ratio,
            "max_rightmost_header_chars": max_rightmost_header_chars,
            "max_missing_per_gap": max_missing_per_gap,
            "margin": margin,
            "ink_threshold": ink_threshold,
            "dark_threshold": dark_threshold,
            "min_dark_pixels": min_dark_pixels,
        },
        "checked_pages": checked_pages,
        "candidate_crops": len(accepted) + len(rejected),
        "accepted_crops": len(accepted),
        "rejected_crops": len(rejected),
        "tasks": accepted,
        "rejected": rejected,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--images-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--api-base")
    parser.add_argument("--min-gap-ratio", type=float, default=1.6)
    parser.add_argument("--max-rightmost-header-chars", type=int, default=20)
    parser.add_argument("--max-missing-per-gap", type=int, default=3)
    parser.add_argument("--margin", type=int, default=4)
    parser.add_argument("--ink-threshold", type=int, default=220)
    parser.add_argument("--dark-threshold", type=int, default=180)
    parser.add_argument("--min-dark-pixels", type=int, default=200)
    args = parser.parse_args(argv)

    report = json.loads(args.report.read_text(encoding="utf-8"))
    downloaded = 0
    if args.api_base:
        downloaded = download_missing_images(
            report, images_dir=args.images_dir, api_base=args.api_base
        )
    manifest = generate_manifest(
        report,
        images_dir=args.images_dir,
        crops_dir=args.output_dir / "crops",
        min_gap_ratio=args.min_gap_ratio,
        max_rightmost_header_chars=args.max_rightmost_header_chars,
        max_missing_per_gap=args.max_missing_per_gap,
        margin=args.margin,
        ink_threshold=args.ink_threshold,
        dark_threshold=args.dark_threshold,
        min_dark_pixels=args.min_dark_pixels,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "gap-crop-manifest.json"
    output_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"downloaded={downloaded}, checked_pages={manifest['checked_pages']}, "
        f"accepted={manifest['accepted_crops']}, "
        f"rejected={manifest['rejected_crops']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
