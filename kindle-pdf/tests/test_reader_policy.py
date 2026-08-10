from kindle_controller.reader_policy import (
    needs_cover_step,
    page_layout_policy,
    previous_page_key,
)


def test_page_layout_policy_keeps_source_specific_controls() -> None:
    comic = page_layout_policy("comic")
    novel = page_layout_policy("novel")

    assert comic is not None
    assert comic.option_id == "aaOption-Split"
    assert comic.compatible_without_option_id is None
    assert novel is not None
    assert novel.option_id == "aaOption-Single"
    assert novel.compatible_without_option_id == "フォント-item"
    assert page_layout_policy("doujin") is None


def test_cover_step_is_limited_to_novel_first_page() -> None:
    assert needs_cover_step("novel", "ページ1/233  • 0%")
    assert not needs_cover_step("novel", "Location 1 of 3304  • 0%")
    assert not needs_cover_step("comic", "ページ1/85  • 0%")


def test_previous_page_key_is_opposite_of_capture_direction() -> None:
    assert previous_page_key("left") == "right"
    assert previous_page_key("right") == "left"
