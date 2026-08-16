from __future__ import annotations

from PIL import Image, ImageDraw

from services.novel_db.surya_quality import (
    crosscheck_ocr_results,
    evaluate_external_ocr,
    evaluate_page_quality,
)
from services.novel_db.surya_types import SuryaBlock, SuryaPageResult


def test_quality_gate_rejects_text_outside_ocr_bbox() -> None:
    image = Image.new("RGB", (200, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 50, 280), fill="black")
    draw.rectangle((150, 20, 180, 280), fill="black")
    raw = '<div data-label="Text" data-bbox="50 50 300 950">本文</div>'

    result = evaluate_page_quality(image, raw, min_ink_coverage=0.85, attempt_count=1)

    assert result.state == "failed"
    assert "low_ink_coverage" in result.quality_flags


def test_quality_gate_accepts_blank_page_with_explicit_flag() -> None:
    image = Image.new("RGB", (200, 300), "white")

    result = evaluate_page_quality(image, "", min_ink_coverage=0.85, attempt_count=1)

    assert result.state == "passed"
    assert result.quality_flags == ["blank_page"]


def test_quality_gate_rejects_nonempty_malformed_html() -> None:
    image = Image.new("RGB", (200, 300), "white")
    ImageDraw.Draw(image).rectangle((20, 20, 180, 280), fill="black")

    result = evaluate_page_quality(
        image,
        '<div data-bbox="<div data-bbox="broken',
        min_ink_coverage=0.85,
        attempt_count=1,
    )

    assert result.state == "failed"
    assert "malformed_output" in result.quality_flags


def test_edge_coverage_accepts_white_text_on_uniform_black_background() -> None:
    image = Image.new("RGB", (200, 300), "black")
    ImageDraw.Draw(image).rectangle((80, 50, 120, 250), fill="white")
    raw = '<div data-label="Text" data-bbox="350 100 650 900">白抜き本文</div>'

    result = evaluate_page_quality(image, raw, min_ink_coverage=0.85, attempt_count=1)

    assert result.state == "passed"
    assert result.ink_coverage is not None and result.ink_coverage > 0.95


def test_quality_gate_rejects_long_text_duplicated_into_another_block() -> None:
    image = Image.new("RGB", (200, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 80, 280), fill="black")
    draw.rectangle((120, 20, 180, 280), fill="black")
    duplicated = "同一の長い文章が別の列へそのまま複製されています"
    raw = (
        f'<div data-label="Text" data-bbox="50 50 450 950">{duplicated}</div>'
        f'<div data-label="Text" data-bbox="550 50 950 950">{duplicated}</div>'
    )

    result = evaluate_page_quality(image, raw, min_ink_coverage=0.85, attempt_count=1)

    assert result.state == "failed"
    assert "duplicate_text_block" in result.quality_flags


def test_quality_gate_rejects_repeated_text_inside_one_block() -> None:
    image = Image.new("RGB", (200, 300), "white")
    ImageDraw.Draw(image).rectangle((20, 20, 180, 280), fill="black")
    repeated = "陛下、同じ文章が繰り返されています。" * 5
    raw = f'<div data-label="Text" data-bbox="50 50 950 950">{repeated}</div>'

    result = evaluate_page_quality(image, raw, min_ink_coverage=0.85, attempt_count=1)

    assert result.state == "failed"
    assert "repeated_text" in result.quality_flags


def test_external_ocr_adjudication_accepts_high_confidence_sparse_vertical_text() -> None:
    image = Image.new("RGB", (400, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((330, 20, 350, 280), fill="black")
    draw.rectangle((360, 20, 380, 280), fill="black")
    items = [
        {
            "text": "本作品 は縦書きでレイアウトされています 。",
            "confidence": 0.999,
            "position": [[330, 20], [350, 20], [350, 280], [330, 280]],
        },
        {
            "text": "表示の差が認められることがあります。",
            "confidence": 0.995,
            "position": [[360, 20], [380, 20], [380, 280], [360, 280]],
        },
    ]

    result = evaluate_external_ocr(
        image,
        items,
        min_ink_coverage=0.85,
        attempt_count=5,
        engine_flag="yomitoku_adjudication",
    )

    assert result.state == "passed"
    assert "yomitoku_adjudication" in result.quality_flags
    assert "本作品は縦書き" in result.full_text
    assert "作品 は" not in result.full_text


def test_external_ocr_adjudication_rejects_low_confidence_result() -> None:
    image = Image.new("RGB", (200, 300), "white")
    ImageDraw.Draw(image).rectangle((150, 20, 180, 280), fill="black")
    items = [
        {
            "text": "不確かな本文",
            "confidence": 0.7,
            "position": [[150, 20], [180, 20], [180, 280], [150, 280]],
        }
    ]

    result = evaluate_external_ocr(
        image,
        items,
        min_ink_coverage=0.85,
        attempt_count=5,
        engine_flag="yomitoku_adjudication",
    )

    assert result.state == "failed"
    assert "external_ocr_low_confidence" in result.quality_flags


def test_external_ocr_adjudication_accepts_confidence_distribution_with_one_low_block() -> None:
    image = Image.new("RGB", (400, 300), "white")
    draw = ImageDraw.Draw(image)
    items = []
    for index, confidence in enumerate([0.99, 0.97, 0.95, 0.92, 0.40]):
        x0 = 350 - index * 50
        draw.rectangle((x0, 20, x0 + 30, 280), fill="black")
        items.append(
            {
                "text": f"十分な長さの縦書き本文です{index}" if confidence >= 0.9 else "短い注記",
                "confidence": confidence,
                "position": [[x0, 20], [x0 + 30, 20], [x0 + 30, 280], [x0, 280]],
            }
        )

    result = evaluate_external_ocr(
        image,
        items,
        min_ink_coverage=0.85,
        attempt_count=2,
        engine_flag="yomitoku_adjudication",
    )

    assert result.state == "passed"
    assert "external_ocr_distribution_accepted" in result.quality_flags


def _page_result(text: str, *, state: str = "passed") -> SuryaPageResult:
    return SuryaPageResult(
        full_text=text,
        raw_output="",
        blocks=[SuryaBlock("Text", (0, 0, 1000, 1000), text)],
        state=state,
        quality_flags=[],
        ink_coverage=1.0,
        attempt_count=1,
        error_message="failed" if state == "failed" else None,
    )


def test_crosscheck_prefers_more_complete_consistent_external_text() -> None:
    primary = _page_result("今はまだ踏みとどまれている。けれども、踏みとどま")
    external = _page_result("今はまだ踏みとどまれている。けれども、踏みとどまらなくていいのだ。")

    result = crosscheck_ocr_results(primary, external, min_similarity=0.7)

    assert result.state == "passed"
    assert result.full_text == external.full_text
    assert "external_ocr_more_complete" in result.quality_flags


def test_crosscheck_rejects_material_engine_disagreement() -> None:
    primary = _page_result("第一章。これは正しい本文です。")
    external = _page_result("目次。まったく異なる文字列です。")

    result = crosscheck_ocr_results(primary, external, min_similarity=0.85)

    assert result.state == "failed"
    assert "cross_engine_disagreement" in result.quality_flags
