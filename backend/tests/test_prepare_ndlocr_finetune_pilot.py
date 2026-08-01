from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "prepare_ndlocr_finetune_pilot.py"
_SPEC = importlib.util.spec_from_file_location("prepare_ndlocr_finetune_pilot", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
pilot = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(pilot)


def test_align_segment_labels_accepts_unambiguous_corrections() -> None:
    result = pilot.align_segment_labels(
        "吾輩は猫である名前はまだない",
        ["吾輩は猫である", "名前わまだない"],
        min_label_chars=2,
    )

    assert [item["label"] for item in result["accepted"]] == [
        "吾輩は猫である",
        "名前はまだない",
    ]
    assert result["rejected"] == []


def test_align_segment_labels_rejects_page_with_large_omission() -> None:
    result = pilot.align_segment_labels(
        "一二三四五六七八九十追加の長い欠落",
        ["一二三四五六七八九十"],
        min_label_chars=2,
    )

    assert result["accepted"] == []
    assert result["reason"] == "page_cer_exceeded"


def test_align_segment_labels_rejects_both_sides_of_missing_boundary_mark() -> None:
    result = pilot.align_segment_labels(
        "「第一列」第二列本文",
        ["「第一列", "第二列本文"],
        min_label_chars=2,
    )

    assert result["accepted"] == []
    assert all("ambiguous_boundary" in item["reasons"] for item in result["rejected"])


def test_select_evenly_is_deterministic_and_includes_edges() -> None:
    pages = [{"page_no": page_no} for page_no in range(1, 11)]

    assert [page["page_no"] for page in pilot.select_evenly(pages, 4)] == [1, 4, 7, 10]


def test_validate_resume_state_accepts_complete_page(tmp_path: Path) -> None:
    images_dir = tmp_path / "images"
    labels_dir = tmp_path / "labels"
    images_dir.mkdir()
    labels_dir.mkdir()
    image_path = images_dir / "r0001-p0002-s000.jpg"
    image_path.write_bytes(b"image")
    (labels_dir / "r0001-p0002-s000.txt").write_text("本文", encoding="utf-8")
    state = {
        "format_version": 1,
        "run_ids": [1],
        "holdout_run_ids": [30],
        "pages_per_run": 10000,
        "samples": [
            {
                "run_id": 1,
                "page_no": 2,
                "image": str(image_path.resolve()),
                "label": "本文",
            }
        ],
        "pages": [{"run_id": 1, "page_no": 2, "image_sha256": "abc"}],
    }

    samples, pages = pilot.validate_resume_state(
        state,
        run_ids=[1],
        holdout_run_ids=[30],
        pages_per_run=10000,
        images_dir=images_dir,
        labels_dir=labels_dir,
    )

    assert len(samples) == 1
    assert len(pages) == 1


def test_validate_resume_state_rejects_holdout_page(tmp_path: Path) -> None:
    state = {
        "format_version": 1,
        "run_ids": [1],
        "holdout_run_ids": [30],
        "pages_per_run": 10000,
        "samples": [],
        "pages": [{"run_id": 30, "page_no": 2, "image_sha256": "abc"}],
    }

    try:
        pilot.validate_resume_state(
            state,
            run_ids=[1],
            holdout_run_ids=[30],
            pages_per_run=10000,
            images_dir=tmp_path / "images",
            labels_dir=tmp_path / "labels",
        )
    except ValueError as error:
        assert "final holdout" in str(error)
    else:
        raise AssertionError("holdout page was accepted")


def test_write_json_atomic_retries_windows_read_collision(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "state.json"
    original_replace = Path.replace
    attempts = 0

    def flaky_replace(path: Path, target: Path) -> Path:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("simulated WinError 5")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)

    pilot._write_json_atomic(output, {"status": "ok"})

    assert attempts == 3
    assert output.read_text(encoding="utf-8").strip().endswith("}")


def test_parse_ndlocr_segments_keeps_vertical_reading_order() -> None:
    payload = {
        "contents": [
            {
                "text": "左",
                "isTextline": "true",
                "isVertical": "true",
                "boundingBox": [[10, 0], [20, 0], [20, 50], [10, 50]],
            },
            {
                "text": "右",
                "isTextline": "true",
                "isVertical": "true",
                "boundingBox": [[90, 0], [100, 0], [100, 50], [90, 50]],
            },
            {
                "text": "横",
                "isTextline": "true",
                "isVertical": "false",
                "boundingBox": [[0, 0], [50, 0], [50, 10], [0, 10]],
            },
        ]
    }

    segments = pilot.parse_ndlocr_segments(payload)

    assert [segment["text"] for segment in segments] == ["右", "左"]
