from services.novel_db.ocr_page_types import is_index_eligible, suggest_page_type


def test_suggests_table_of_contents_from_heading_list() -> None:
    assert (
        suggest_page_type(
            page_no=4,
            page_count=100,
            full_text="第一章 はじまり\n第二章 旅立ち\n第三章 帰還",
            char_count=30,
        )
        == "toc"
    )


def test_suggests_colophon_from_late_publication_metadata() -> None:
    assert (
        suggest_page_type(
            page_no=98,
            page_count=100,
            full_text="発行所 サンプル文庫\nISBN 000-0-00-000000-0",
            char_count=40,
        )
        == "colophon_or_ad"
    )


def test_suggests_illustration_for_nearly_empty_page() -> None:
    assert (
        suggest_page_type(
            page_no=20,
            page_count=100,
            full_text="＊",
            char_count=1,
        )
        == "illustration"
    )


def test_suggests_narrative_only_when_text_is_substantial() -> None:
    assert (
        suggest_page_type(
            page_no=20,
            page_count=100,
            full_text="これは本文です。" * 50,
            char_count=400,
        )
        == "narrative"
    )
    assert (
        suggest_page_type(
            page_no=20,
            page_count=100,
            full_text="短い章題",
            char_count=5,
        )
        == "illustration"
    )


def test_only_narrative_is_index_eligible() -> None:
    assert is_index_eligible("narrative") is True
    for page_type in ("unknown", "toc", "illustration", "colophon_or_ad"):
        assert is_index_eligible(page_type) is False
