from pathlib import Path
from random import Random

import pytest
from PIL import Image, ImageDraw

from capture_quality import CaptureQualityError, audit_capture_images


def _save(path: Path, color: tuple[int, int, int], size=(24, 32)) -> None:
    Image.new("RGB", size, color=color).save(path)


def _save_distinct_page(
    path: Path,
    page_no: int,
    *,
    overlay: bool = False,
) -> None:
    image = Image.new("RGB", (512, 384), color=(255, 255, 255))
    random = Random(page_no)
    body = Image.frombytes("RGB", (300, 200), random.randbytes(300 * 200 * 3))
    image.paste(body, (90, 80))
    draw = ImageDraw.Draw(image)
    if overlay:
        draw.rectangle(
            (370, 275, 511, 383),
            fill=(245, 245, 245),
            outline=(20, 20, 20),
            width=3,
        )
        draw.rectangle((382, 290, 405, 313), fill=(35, 90, 210))
        for offset, width in ((0, 86), (16, 94), (32, 72), (60, 90)):
            draw.rectangle(
                (416, 290 + offset, 416 + width, 294 + offset),
                fill=(30, 30, 30),
            )
    image.save(path)


def test_audit_is_deterministic_with_bounded_parallel_workers(tmp_path) -> None:
    _save(tmp_path / "001.png", (255, 255, 255))
    _save(tmp_path / "002.png", (1, 2, 3))
    _save(tmp_path / "003.png", (1, 2, 3))

    serial = audit_capture_images(tmp_path, expected_count=3, max_workers=1)
    parallel = audit_capture_images(tmp_path, expected_count=3, max_workers=4)

    assert serial == parallel
    assert [item["name"] for item in parallel.files] == [
        "001.png",
        "002.png",
        "003.png",
    ]
    assert {finding["code"] for finding in parallel.findings} >= {
        "blank_or_sparse_candidate",
        "exact_duplicate_candidate",
    }


def test_audit_rejects_missing_sequence(tmp_path) -> None:
    _save(tmp_path / "001.png", (1, 2, 3))
    _save(tmp_path / "003.png", (4, 5, 6))

    with pytest.raises(CaptureQualityError, match="連番"):
        audit_capture_images(tmp_path, expected_count=2)


def test_audit_rejects_corrupt_image(tmp_path) -> None:
    (tmp_path / "001.png").write_bytes(b"not-a-png")

    with pytest.raises(CaptureQualityError, match="復号"):
        audit_capture_images(tmp_path, expected_count=1)


def test_audit_rejects_dimension_mismatch(tmp_path) -> None:
    _save(tmp_path / "001.png", (1, 2, 3), size=(24, 32))
    _save(tmp_path / "002.png", (4, 5, 6), size=(25, 32))

    with pytest.raises(CaptureQualityError, match="寸法"):
        audit_capture_images(tmp_path, expected_count=2)


def test_audit_rejects_capture_evidence_count_mismatch(tmp_path) -> None:
    _save(tmp_path / "001.png", (1, 2, 3))

    with pytest.raises(CaptureQualityError, match="件数"):
        audit_capture_images(tmp_path, expected_count=2)


def test_novel_edge_content_is_warning_only(tmp_path) -> None:
    image = Image.new("RGB", (100, 100), color=(255, 255, 255))
    for x in range(100):
        image.putpixel((x, 0), (0, 0, 0))
        image.putpixel((x, 1), (0, 0, 0))
    image.save(tmp_path / "001.png")

    result = audit_capture_images(
        tmp_path,
        expected_count=1,
        source="novel",
    )

    assert "novel_edge_content_candidate" in {
        finding["code"] for finding in result.findings
    }


def test_repeated_structured_edge_overlay_is_blocking(tmp_path) -> None:
    for page_no in range(1, 13):
        _save_distinct_page(
            tmp_path / f"{page_no:03}.png",
            page_no,
            overlay=page_no <= 8,
        )

    with pytest.raises(CaptureQualityError, match="repeated_screen_overlay_detected"):
        audit_capture_images(tmp_path, expected_count=12, max_workers=1)


def test_partial_repeated_overlay_is_warning_only(tmp_path) -> None:
    for page_no in range(1, 13):
        _save_distinct_page(
            tmp_path / f"{page_no:03}.png",
            page_no,
            overlay=page_no <= 3,
        )

    result = audit_capture_images(tmp_path, expected_count=12, max_workers=1)

    assert "repeated_screen_overlay_candidate" in {
        finding["code"] for finding in result.findings
    }
    detector = result.to_manifest()["overlay_detector"]
    assert detector["policy_version"] == "kindle-repeated-overlay-v1"
    assert detector["passed"] is True
    assert detector["sampled_page_count"] == 12
    assert detector["candidate_count"] >= 1
    assert detector["blocking_candidate_count"] == 0


def test_exact_duplicate_pages_do_not_become_overlay_failure(tmp_path) -> None:
    duplicate = tmp_path / "001.png"
    _save_distinct_page(duplicate, 1)
    duplicate_bytes = duplicate.read_bytes()
    for page_no in range(2, 9):
        (tmp_path / f"{page_no:03}.png").write_bytes(duplicate_bytes)

    result = audit_capture_images(tmp_path, expected_count=8, max_workers=1)

    codes = {finding["code"] for finding in result.findings}
    assert "exact_duplicate_candidate" in codes
    assert "repeated_screen_overlay_candidate" not in codes


def test_varying_page_content_and_blank_margins_do_not_trigger_overlay(
    tmp_path,
) -> None:
    for page_no in range(1, 13):
        _save_distinct_page(tmp_path / f"{page_no:03}.png", page_no)

    result = audit_capture_images(tmp_path, expected_count=12, max_workers=4)

    assert result.to_manifest()["policy_version"] == "kindle-image-qa-v1"
    assert result.to_manifest()["overlay_detector"]["candidate_count"] == 0
