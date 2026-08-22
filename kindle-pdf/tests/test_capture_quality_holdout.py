from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from capture_quality_holdout import (
    build_holdout_manifest,
    evaluate_holdout_manifest,
    main,
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


@pytest.mark.parametrize(
    ("labels", "message"),
    [
        (
            [{"code": "unknown_candidate", "files": ["001.png"]}],
            "unsupported capture quality label code",
        ),
        (
            [{"code": "blank_or_sparse_candidate", "files": ["999.png"]}],
            "label file is not in image inventory",
        ),
        (
            [
                {"code": "blank_or_sparse_candidate", "files": ["001.png"]},
                {"code": "blank_or_sparse_candidate", "files": ["001.png"]},
            ],
            "duplicate capture quality label",
        ),
    ],
)
def test_holdout_rejects_invalid_labels(
    tmp_path: Path,
    labels: list[dict],
    message: str,
) -> None:
    case_dir = tmp_path / "case-a"
    case_dir.mkdir()
    _save(case_dir / "001.png", (255, 255, 255))

    with pytest.raises(ValueError, match=message):
        build_holdout_manifest(
            {
                "holdout_id": "capture-warning-holdout",
                "cases": [
                    {
                        "case_id": "case-a",
                        "source": "comic",
                        "image_dir": "case-a",
                        "expected_count": 1,
                        "labels": labels,
                    }
                ],
            },
            image_root=tmp_path,
        )


def test_holdout_rejects_invalid_source_before_evaluation(tmp_path: Path) -> None:
    case_dir = tmp_path / "case-a"
    case_dir.mkdir()
    _save(case_dir / "001.png", (255, 255, 255))

    with pytest.raises(ValueError, match="capture quality source"):
        build_holdout_manifest(
            {
                "holdout_id": "capture-warning-holdout",
                "cases": [
                    {
                        "case_id": "case-a",
                        "source": "doujin",
                        "image_dir": "case-a",
                        "expected_count": 1,
                        "labels": [],
                    }
                ],
            },
            image_root=tmp_path,
        )


def test_holdout_rejects_invalid_label_in_signed_manifest(tmp_path: Path) -> None:
    case_dir = tmp_path / "case-a"
    case_dir.mkdir()
    _save(case_dir / "001.png", (255, 255, 255))
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
    manifest["cases"][0]["labels"] = [
        {"code": "unknown_candidate", "files": ["001.png"]}
    ]
    content = {
        key: value for key, value in manifest.items() if key != "manifest_sha256"
    }
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps(
            content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    with pytest.raises(ValueError, match="unsupported capture quality label code"):
        evaluate_holdout_manifest(manifest, image_root=tmp_path)


def test_holdout_fails_closed_when_case_cannot_be_audited(tmp_path: Path) -> None:
    case_dir = tmp_path / "case-a"
    case_dir.mkdir()
    _save(case_dir / "001.png", (64, 64, 64))
    Image.new("RGB", (81, 100), color=(128, 128, 128)).save(case_dir / "002.png")
    manifest = build_holdout_manifest(
        {
            "holdout_id": "capture-warning-holdout",
            "cases": [
                {
                    "case_id": "case-a",
                    "source": "comic",
                    "image_dir": "case-a",
                    "expected_count": 2,
                    "labels": [],
                }
            ],
        },
        image_root=tmp_path,
    )

    with pytest.raises(ValueError, match="holdout case is not auditable"):
        evaluate_holdout_manifest(manifest, image_root=tmp_path)


def test_holdout_preserves_provenance_in_report(tmp_path: Path) -> None:
    case_dir = tmp_path / "case-a"
    case_dir.mkdir()
    _save(case_dir / "001.png", (128, 128, 128))
    provenance = {
        "dataset_role": "real_image_holdout",
        "ground_truth_kind": "ai_visual_labels",
        "reviewer_kind": "Codex visual QA (AI-assisted)",
        "human_confirmation": "pending",
        "selection_manifest_sha256": "a" * 64,
        "label_manifest_sha256": "b" * 64,
        "reviewed_at": "2026-08-22T12:00:00+09:00",
    }
    manifest = build_holdout_manifest(
        {
            "holdout_id": "capture-warning-holdout",
            "provenance": provenance,
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

    report = evaluate_holdout_manifest(manifest, image_root=tmp_path)

    assert manifest["provenance"] == provenance
    assert report["provenance"] == provenance


def test_holdout_rejects_invalid_provenance(tmp_path: Path) -> None:
    case_dir = tmp_path / "case-a"
    case_dir.mkdir()
    _save(case_dir / "001.png", (128, 128, 128))

    with pytest.raises(ValueError, match="dataset role"):
        build_holdout_manifest(
            {
                "holdout_id": "capture-warning-holdout",
                "provenance": {
                    "dataset_role": "regression",
                    "ground_truth_kind": "ai_visual_labels",
                    "reviewer_kind": "Codex visual QA (AI-assisted)",
                    "human_confirmation": "pending",
                },
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


def test_holdout_cli_builds_manifest_atomically(tmp_path: Path) -> None:
    case_dir = tmp_path / "case-a"
    case_dir.mkdir()
    _save(case_dir / "001.png", (255, 255, 255))
    spec_path = tmp_path / "spec.json"
    manifest_path = tmp_path / "manifest.json"
    spec_path.write_text(
        json.dumps(
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
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "--build-spec",
                str(spec_path),
                "--image-root",
                str(tmp_path),
                "--manifest-output",
                str(manifest_path),
            ]
        )
        == 0
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "kindle-capture-quality-holdout-v1"
    assert manifest["cases"][0]["images"][0]["name"] == "001.png"
    assert not manifest_path.with_suffix(".json.tmp").exists()

    report_path = tmp_path / "report.json"
    assert (
        main(
            [
                "--manifest",
                str(manifest_path),
                "--image-root",
                str(tmp_path),
                "--output",
                str(report_path),
            ]
        )
        == 0
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["manifest_sha256"] == manifest["manifest_sha256"]
    assert not report_path.with_suffix(".json.tmp").exists()
