from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from capture_quality_holdout import (
    build_holdout_manifest,
    evaluate_holdout_manifest,
)


def _save(path: Path, color: tuple[int, int, int]) -> None:
    Image.new("RGB", (80, 100), color=color).save(path)


def test_holdout_reports_code_level_precision_and_recall(tmp_path: Path) -> None:
    case_dir = tmp_path / "case-a"
    case_dir.mkdir()
    _save(case_dir / "001.png", (255, 255, 255))
    (case_dir / "002.png").write_bytes((case_dir / "001.png").read_bytes())
    spec = {
        "holdout_id": "capture-warning-holdout",
        "cases": [
            {
                "case_id": "case-a",
                "source": "comic",
                "image_dir": "case-a",
                "expected_count": 2,
                "labels": [
                    {
                        "code": "blank_or_sparse_candidate",
                        "files": ["001.png"],
                    },
                    {
                        "code": "blank_or_sparse_candidate",
                        "files": ["002.png"],
                    },
                    {
                        "code": "exact_duplicate_candidate",
                        "files": ["001.png", "002.png"],
                    },
                ],
            }
        ],
    }
    manifest = build_holdout_manifest(spec, image_root=tmp_path)

    report = evaluate_holdout_manifest(manifest, image_root=tmp_path)
    metrics = {item["code"]: item for item in report["metrics"]}

    assert metrics["blank_or_sparse_candidate"] == {
        "code": "blank_or_sparse_candidate",
        "true_positive": 2,
        "false_positive": 0,
        "false_negative": 0,
        "precision": 1.0,
        "recall": 1.0,
    }
    assert metrics["exact_duplicate_candidate"]["recall"] == 1.0
    assert report["case_count"] == 1
    assert report["image_count"] == 2


def test_holdout_rejects_changed_image(tmp_path: Path) -> None:
    case_dir = tmp_path / "case-a"
    case_dir.mkdir()
    _save(case_dir / "001.png", (255, 255, 255))
    manifest = build_holdout_manifest(
        {
            "holdout_id": "capture-warning-holdout",
            "cases": [
                {
                    "case_id": "case-a",
                    "source": "novel",
                    "image_dir": "case-a",
                    "expected_count": 1,
                    "labels": [],
                }
            ],
        },
        image_root=tmp_path,
    )
    _save(case_dir / "001.png", (0, 0, 0))

    with pytest.raises(ValueError, match="image digest"):
        evaluate_holdout_manifest(manifest, image_root=tmp_path)


def test_holdout_is_read_only(tmp_path: Path) -> None:
    case_dir = tmp_path / "case-a"
    case_dir.mkdir()
    _save(case_dir / "001.png", (128, 128, 128))
    manifest = build_holdout_manifest(
        {
            "holdout_id": "capture-warning-holdout",
            "cases": [
                {
                    "case_id": "case-a",
                    "source": "comic",
                    "image_dir": "case-a",
                    "expected_count": 1,
                    "labels": [],
                }
            ],
        },
        image_root=tmp_path,
    )
    before = (case_dir / "001.png").read_bytes()

    evaluate_holdout_manifest(manifest, image_root=tmp_path)

    assert (case_dir / "001.png").read_bytes() == before
    assert sorted(path.name for path in case_dir.iterdir()) == ["001.png"]
