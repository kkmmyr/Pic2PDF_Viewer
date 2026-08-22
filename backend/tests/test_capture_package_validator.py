import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from services.kindle_catalog.capture_package_validator import (
    build_quality_audit,
    validate_ready_dir,
)


def _job() -> dict:
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "asin": "B000CAPTURE",
        "source": "novel",
        "captured_screens": 1,
    }


def _ready_package(tmp_path: Path) -> tuple[Path, dict]:
    ready = tmp_path / "job.ready"
    image_path = ready / "images" / "001.png"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (20, 30), color=(1, 2, 3)).save(image_path)
    manifest = {
        "manifest_version": 2,
        "job_id": _job()["id"],
        "asin": _job()["asin"],
        "source": _job()["source"],
        "capture": {
            "policy_version": "kindle-completeness-v1",
            "termination_reason": "visual_no_change_after_retries",
            "end_of_book_proven": True,
            "captured_screens": 1,
            "expected_screens": None,
            "direction": "left",
            "layout": "single",
            "crop_bounds": [0, 0, 20, 30],
            "image_size": [20, 30],
            "last_saved_file": "001.png",
            "unchanged_observation_windows": 2,
            "termination_unchanged_windows": 2,
            "observation_timeout_seconds": 5.0,
            "retry_limit": 1,
            "turn_commands": 2,
            "successful_transitions": 0,
            "retry_commands": 1,
            "opposite_direction_commands": 0,
            "canary": {
                "policy_version": "kindle-capture-canary-v1",
                "passed": True,
                "dimensions": [20, 30],
                "crop_bounds": [0, 0, 20, 30],
                "first_sha256": "a" * 64,
                "second_sha256": "b" * 64,
                "mean_difference": 1.0,
                "changed_ratio": 0.1,
            },
        },
        "quality": {
            "schema_version": 1,
            "policy_version": "kindle-image-qa-v1",
            "warning_policy_version": "kindle-image-warning-v1",
            "outcome": "passed",
            "page_count": 1,
            "dimensions": [20, 30],
            "findings": [],
            "overlay_detector": {
                "policy_version": "kindle-repeated-overlay-v1",
                "passed": True,
                "sampled_page_count": 1,
                "candidate_count": 0,
                "blocking_candidate_count": 0,
            },
        },
        "files": [
            {
                "name": "001.png",
                "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                "width": 20,
                "height": 30,
                "size": image_path.stat().st_size,
            }
        ],
    }
    (ready / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return ready, manifest


def _rewrite(ready: Path, manifest: dict) -> None:
    (ready / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_validator_accepts_independently_verified_v2_package(tmp_path) -> None:
    ready, _manifest = _ready_package(tmp_path)

    manifest, files = validate_ready_dir(_job(), ready)

    assert manifest["manifest_version"] == 2
    assert [path.name for path in files] == ["001.png"]


def test_validator_rejects_legacy_manifest(tmp_path) -> None:
    ready, manifest = _ready_package(tmp_path)
    manifest.pop("manifest_version")
    _rewrite(ready, manifest)

    with pytest.raises(ValueError, match="manifest_version"):
        validate_ready_dir(_job(), ready)


def test_validator_rejects_unproven_end_of_book(tmp_path) -> None:
    ready, manifest = _ready_package(tmp_path)
    manifest["capture"]["end_of_book_proven"] = False
    _rewrite(ready, manifest)

    with pytest.raises(ValueError, match="証明"):
        validate_ready_dir(_job(), ready)


def test_validator_rejects_missing_canary(tmp_path) -> None:
    ready, manifest = _ready_package(tmp_path)
    manifest["capture"].pop("canary")
    _rewrite(ready, manifest)

    with pytest.raises(ValueError, match="カナリア"):
        validate_ready_dir(_job(), ready)


def test_validator_rejects_corrupt_image_even_with_matching_hash(tmp_path) -> None:
    ready, manifest = _ready_package(tmp_path)
    image_path = ready / "images" / "001.png"
    image_path.write_bytes(b"not-an-image")
    manifest["files"][0]["sha256"] = hashlib.sha256(image_path.read_bytes()).hexdigest()
    manifest["files"][0]["size"] = image_path.stat().st_size
    _rewrite(ready, manifest)

    with pytest.raises(ValueError, match="復号"):
        validate_ready_dir(_job(), ready)


def test_validator_rejects_job_count_mismatch(tmp_path) -> None:
    ready, _manifest = _ready_package(tmp_path)
    job = _job()
    job["captured_screens"] = 2

    with pytest.raises(ValueError, match="ジョブ"):
        validate_ready_dir(job, ready)


def test_validator_rejects_missing_overlay_detector_evidence(tmp_path) -> None:
    ready, manifest = _ready_package(tmp_path)
    manifest["quality"].pop("overlay_detector")
    _rewrite(ready, manifest)

    with pytest.raises(ValueError, match="overlay"):
        validate_ready_dir(_job(), ready)


def test_validator_rejects_blocking_overlay_candidate(tmp_path) -> None:
    ready, manifest = _ready_package(tmp_path)
    manifest["quality"]["overlay_detector"]["passed"] = False
    manifest["quality"]["overlay_detector"]["blocking_candidate_count"] = 1
    _rewrite(ready, manifest)

    with pytest.raises(ValueError, match="overlay"):
        validate_ready_dir(_job(), ready)


def test_quality_audit_groups_valid_findings_by_code(tmp_path) -> None:
    ready, manifest = _ready_package(tmp_path)
    manifest["quality"]["findings"] = [
        {
            "code": "blank_or_sparse_candidate",
            "severity": "warning",
            "files": ["001.png"],
            "metrics": {"mean_luma": 255.0},
        },
        {
            "code": "blank_or_sparse_candidate",
            "severity": "warning",
            "files": ["001.png"],
        },
    ]
    _rewrite(ready, manifest)

    validated, _files = validate_ready_dir(_job(), ready)
    audit = build_quality_audit(validated)

    assert audit["qa_policy_version"] == "kindle-image-qa-v1"
    assert len(audit["quality_sha256"]) == 64
    assert audit["warnings"] == [
        {
            "code": "blank_or_sparse_candidate",
            "finding_count": 2,
            "files": ["001.png"],
            "findings": manifest["quality"]["findings"],
        }
    ]


@pytest.mark.parametrize(
    "finding",
    [
        {
            "code": "unknown_candidate",
            "severity": "warning",
            "files": ["001.png"],
        },
        {
            "code": "blank_or_sparse_candidate",
            "severity": "blocking",
            "files": ["001.png"],
        },
        {
            "code": "blank_or_sparse_candidate",
            "severity": "warning",
            "files": ["999.png"],
        },
        {
            "code": "blank_or_sparse_candidate",
            "severity": "warning",
            "files": ["001.png"],
            "metrics": None,
        },
    ],
)
def test_validator_rejects_invalid_warning_evidence(tmp_path, finding) -> None:
    ready, manifest = _ready_package(tmp_path)
    manifest["quality"]["findings"] = [finding]
    _rewrite(ready, manifest)

    with pytest.raises(ValueError, match="warning証跡"):
        validate_ready_dir(_job(), ready)
