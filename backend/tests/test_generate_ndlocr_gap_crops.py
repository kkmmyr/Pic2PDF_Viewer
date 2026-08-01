from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

from PIL import Image, ImageDraw

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "generate_ndlocr_gap_crops.py"
SPEC = importlib.util.spec_from_file_location("generate_ndlocr_gap_crops", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
gap_crops = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gap_crops)


def _segment(center_x: float, text: str = "本文") -> dict[str, object]:
    return {
        "text": text,
        "is_vertical": True,
        "bbox": [
            [center_x - 4, 10],
            [center_x + 4, 10],
            [center_x + 4, 90],
            [center_x - 4, 90],
        ],
    }


def test_infer_missing_columns_detects_wide_interior_gap() -> None:
    inferred = gap_crops.infer_missing_columns(
        [_segment(90), _segment(80), _segment(60), _segment(50)],
        min_gap_ratio=1.6,
        max_rightmost_header_chars=20,
    )

    assert len(inferred) == 1
    assert inferred[0]["center_x"] == 70
    assert inferred[0]["gap_ratio"] == 2


def test_infer_missing_columns_ignores_short_rightmost_heading_gap() -> None:
    inferred = gap_crops.infer_missing_columns(
        [_segment(100, "章"), _segment(80), _segment(70), _segment(60)],
        min_gap_ratio=1.6,
        max_rightmost_header_chars=20,
    )

    assert inferred == []


def test_crop_inferred_column_rejects_sparse_artifact() -> None:
    image = Image.new("RGB", (40, 100), "white")
    image.putpixel((20, 50), (0, 0, 0))

    crop, details = gap_crops.crop_inferred_column(
        image,
        {"center_x": 20, "column_width": 8, "top": 0, "bottom": 99},
        margin=2,
        ink_threshold=220,
        dark_threshold=180,
        min_dark_pixels=10,
    )

    assert crop is None
    assert details["reason"] == "insufficient_dark_pixels"


def test_generate_manifest_writes_only_dense_crop(tmp_path: Path) -> None:
    images_dir = tmp_path / "images"
    crops_dir = tmp_path / "crops"
    images_dir.mkdir()
    image_path = images_dir / "0001.png"
    image = Image.new("RGB", (120, 100), "white")
    draw = ImageDraw.Draw(image)
    for y in range(15, 86, 5):
        draw.rectangle((68, y, 72, y + 2), fill="black")
    image.save(image_path)
    image_sha = hashlib.sha256(image_path.read_bytes()).hexdigest()
    report = {
        "pages": [
            {
                "entry_id": 1,
                "run_id": 4,
                "page_no": 9,
                "image_sha256": image_sha,
                "segments": [
                    _segment(90),
                    _segment(80),
                    _segment(60),
                    _segment(50),
                ],
            }
        ]
    }

    manifest = gap_crops.generate_manifest(
        report,
        images_dir=images_dir,
        crops_dir=crops_dir,
        min_gap_ratio=1.6,
        max_rightmost_header_chars=20,
        max_missing_per_gap=3,
        margin=4,
        ink_threshold=220,
        dark_threshold=180,
        min_dark_pixels=20,
    )

    assert manifest["diagnostic_only"] is True
    assert manifest["publishes_ocr"] is False
    assert manifest["candidate_crops"] == 1
    assert manifest["accepted_crops"] == 1
    assert manifest["rejected_crops"] == 0
    assert Path(manifest["tasks"][0]["crop_path"]).is_file()
