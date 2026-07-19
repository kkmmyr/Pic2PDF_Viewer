from services.novel_db.character_names import NAME_MAX_LENGTH, parse_character_names


def test_parse_character_names_normalizes_separators_and_quotes():
    assert parse_character_names("「アリス」、 ボブ・『キャロル』") == ["アリス", "ボブ", "キャロル"]


def test_parse_character_names_deduplicates_and_skips_invalid_values():
    too_long = "長" * (NAME_MAX_LENGTH + 1)
    assert parse_character_names(f"アリス,アリス, ,{too_long}") == ["アリス"]


def test_parse_character_names_accepts_missing_value():
    assert parse_character_names(None) == []
    assert parse_character_names("") == []
