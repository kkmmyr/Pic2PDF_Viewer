from services.novel_db.ocr_candidate_selection import (
    is_external_materially_more_complete,
    is_external_safe_repetition_fallback,
)


def _unique_content(length: int, *, start: int = 0) -> str:
    return "".join(chr(0x4E00 + start + index) for index in range(length))


def test_external_completeness_ignores_whitespace() -> None:
    primary = ("主 " * 256).strip()
    external = ("主\n" * 256) + ("外\n" * 30)

    assert is_external_materially_more_complete(primary, external)


def test_external_completeness_requires_minimum_primary_length() -> None:
    assert not is_external_materially_more_complete("主" * 255, "外" * 300)


def test_external_completeness_requires_absolute_advantage() -> None:
    assert not is_external_materially_more_complete("主" * 1_000, "外" * 1_029)


def test_external_completeness_requires_relative_advantage() -> None:
    assert not is_external_materially_more_complete("主" * 2_000, "外" * 2_030)


def test_external_repetition_fallback_accepts_non_repeated_full_page() -> None:
    repeated_line = "主系OCRが同じ長い文章を異常に反復しています。" * 3
    primary = "\n".join([repeated_line] * 3)

    assert is_external_safe_repetition_fallback(primary, _unique_content(256))


def test_external_repetition_fallback_rejects_short_external() -> None:
    repeated_line = "主系OCRが同じ長い文章を異常に反復しています。" * 3
    primary = "\n".join([repeated_line] * 3)

    assert not is_external_safe_repetition_fallback(primary, "外" * 255)


def test_external_repetition_fallback_rejects_repeated_external() -> None:
    primary_line = "主系OCRが同じ長い文章を異常に反復しています。" * 3
    external_line = "外部OCRも同じ長い文章を異常に反復しています。" * 3

    assert not is_external_safe_repetition_fallback(
        "\n".join([primary_line] * 3),
        "\n".join([external_line] * 3),
    )
