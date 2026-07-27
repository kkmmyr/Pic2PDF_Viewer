from services.novel_db.character_names import (
    NAME_MAX_LENGTH,
    derive_character_evidence_aliases,
    normalize_character_entries,
    normalize_character_name,
    parse_character_names,
)


def test_parse_character_names_normalizes_separators_and_quotes():
    assert parse_character_names("「アリス」、 ジャン・ピエール, 『キャロル』") == [
        "アリス",
        "ジャン・ピエール",
        "キャロル",
    ]


def test_parse_character_names_deduplicates_and_skips_invalid_values():
    too_long = "長" * (NAME_MAX_LENGTH + 1)
    assert parse_character_names(f"アリス,アリス, ,{too_long}") == ["アリス"]


def test_parse_character_names_accepts_missing_value():
    assert parse_character_names(None) == []
    assert parse_character_names("") == []


def test_normalize_character_name_strips_title_honorific_and_role_note():
    assert normalize_character_name("第一皇子 守伸殿") == "守伸"
    assert normalize_character_name("茉莉花様（主人公）") == "茉莉花"
    assert normalize_character_name("ジャン・ピエール") == "ジャン・ピエール"


def test_normalize_character_name_rejects_anonymous_roles():
    assert normalize_character_name("国王陛下") is None
    assert normalize_character_name("隣国の皇帝") is None
    assert normalize_character_name("女官長") is None


def test_normalize_character_entries_merges_aliases_and_summaries():
    entries = normalize_character_entries(
        {
            "第一皇子 守伸": "第一皇子。",
            "守伸殿": "茉莉花を支える。",
            "国王陛下": "匿名の役職。",
        }
    )

    assert len(entries) == 1
    assert entries[0].name == "守伸"
    assert entries[0].summary == "第一皇子。\n茉莉花を支える。"
    assert entries[0].aliases == ("第一皇子 守伸", "守伸", "守伸殿")


def test_derive_character_evidence_aliases_uses_common_short_forms():
    assert derive_character_evidence_aliases("皓茉莉花") == ("茉莉花",)
    assert derive_character_evidence_aliases("ラーナシュ・ヴァルマ") == ("ラーナシュ",)
    assert derive_character_evidence_aliases("珀陽") == ()
