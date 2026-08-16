from services.novel_db.surya_parsing import parse_surya_html, parse_surya_layout


def test_parse_surya_html_keeps_body_and_discards_ruby_reading() -> None:
    raw = '<div data-label="Text" data-bbox="100 100 900 900">彼女は<ruby>莉杏<rt>りあん</rt></ruby>と呼ばれた。</div>'

    blocks = parse_surya_html(raw)

    assert len(blocks) == 1
    assert blocks[0].text == "彼女は莉杏と呼ばれた。"
    assert blocks[0].bbox == (100.0, 100.0, 900.0, 900.0)


def test_parse_surya_layout_detects_layout_task_output() -> None:
    raw = '[{"label":"Text","bbox":"100 20 900 980","count":250}]'

    blocks = parse_surya_layout(raw)

    assert len(blocks) == 1
    assert blocks[0].label == "Text"
    assert blocks[0].bbox == (100.0, 20.0, 900.0, 980.0)
    assert blocks[0].count == 250


def test_parse_surya_layout_does_not_reclassify_valid_html() -> None:
    raw = '<div data-label="Text" data-bbox="100 20 900 980">[{"label":"Text","bbox":"1 2 3 4","count":1}]</div>'

    assert parse_surya_layout(raw) == []
