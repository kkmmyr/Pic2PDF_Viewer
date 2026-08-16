from services.novel_db.ocr_layout_types import suggest_layout_type, validate_layout_type
from services.novel_db.ocr_worker import select_layout_ocr_result
from services.novel_db.surya_types import SuryaPageResult


def test_mixed_illustration_is_detected_from_non_text_block() -> None:
    raw_output = (
        '<div data-label="Picture" data-bbox="0 0 500 1000"></div>'
        '<div data-label="Text" data-bbox="500 0 1000 1000">本文</div>'
    )
    assert (
        suggest_layout_type(
            raw_output=raw_output,
            full_text="本文" * 80,
            char_count=160,
        )
        == "mixed_illustration"
    )


def test_semantic_toc_is_structured_even_without_layout_label() -> None:
    assert (
        suggest_layout_type(
            raw_output="",
            full_text="目次",
            char_count=2,
            page_type="toc",
        )
        == "structured"
    )


def test_normal_prose_requires_sufficient_text() -> None:
    assert (
        suggest_layout_type(
            raw_output='<div data-label="Text" data-bbox="800 0 900 1000">本文</div>',
            full_text="縦書き本文" * 80,
            char_count=400,
        )
        == "normal_prose"
    )


def test_validate_layout_type_rejects_unknown_value() -> None:
    try:
        validate_layout_type("comic")
    except ValueError as exc:
        assert "invalid OCR layout type" in str(exc)
    else:
        raise AssertionError("invalid layout type was accepted")


def test_mixed_illustration_selects_external_candidate() -> None:
    primary = SuryaPageResult(
        full_text="本文欠落",
        raw_output="",
        blocks=[],
        state="passed",
        quality_flags=[],
        ink_coverage=1.0,
        attempt_count=1,
    )
    external = SuryaPageResult(
        full_text="挿絵の横にある完全な本文",
        raw_output="",
        blocks=[],
        state="passed",
        quality_flags=["yomitoku_adjudication"],
        ink_coverage=1.0,
        attempt_count=2,
    )
    selected, engine = select_layout_ocr_result(
        primary,
        external,
        layout_type="mixed_illustration",
        min_similarity=0.85,
    )
    assert engine == "external"
    assert selected.full_text == external.full_text
    assert "layout_selected_external" in selected.quality_flags


def test_mixed_illustration_does_not_select_shorter_external_candidate() -> None:
    primary = SuryaPageResult(
        full_text="これは挿絵の横にある完全な本文です",
        raw_output="",
        blocks=[],
        state="passed",
        quality_flags=[],
        ink_coverage=1.0,
        attempt_count=1,
    )
    external = SuryaPageResult(
        full_text="これは挿絵の横にある完全な本文",
        raw_output="",
        blocks=[],
        state="passed",
        quality_flags=[],
        ink_coverage=1.0,
        attempt_count=2,
    )
    selected, engine = select_layout_ocr_result(
        primary,
        external,
        layout_type="mixed_illustration",
        min_similarity=0.85,
    )
    assert engine == "primary"
    assert selected.full_text == primary.full_text
