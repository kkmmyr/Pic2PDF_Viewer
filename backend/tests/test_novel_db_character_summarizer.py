"""services/novel_db/character_summarizer.py の単体テスト（B-15）。

Qwen 呼び出し（`_BACKEND.ask`）はモックする。本テストは:
- _parse_main_characters: パーサーの境界
- list_book_characters_in_db: 集計とソート
- collect_character_pages: フィルタ
- top_scenes_for_character: char_count 順の top N
- upsert_character: 冪等 / summary 保存と統計更新の両立
- summarize_character: pages 空・正常系の挙動
を確認する。
"""
from unittest.mock import patch

import pytest

from services.novel_db import with_db
from services.novel_db.character_db import (
    CharacterStat,
    _parse_main_characters,
    collect_character_pages,
    get_character,
    list_book_characters_in_db,
    list_characters,
    top_scenes_for_character,
    upsert_character,
)
from services.novel_db.character_summarizer import summarize_character
from services.novel_db.migrations import upgrade_head

# ---------------------------------------------------------------------------
# _parse_main_characters
# ---------------------------------------------------------------------------

def test_parse_main_characters_comma_separated():
    assert _parse_main_characters("レティ, デューク, アストリッド") == [
        "レティ", "デューク", "アストリッド",
    ]


def test_parse_main_characters_handles_japanese_separators():
    assert _parse_main_characters("レティ、デューク・アストリッド") == [
        "レティ", "デューク", "アストリッド",
    ]


def test_parse_main_characters_returns_empty_for_null():
    assert _parse_main_characters(None) == []
    assert _parse_main_characters("") == []


def test_parse_main_characters_skips_too_long_fragments():
    # 30 字超は誤抽出と判断してスキップ
    long_name = "あ" * 31
    assert _parse_main_characters(f"レティ, {long_name}, デューク") == [
        "レティ", "デューク",
    ]


# ---------------------------------------------------------------------------
# DB を使うテスト用フィクスチャ
# ---------------------------------------------------------------------------

@pytest.fixture
def db_with_characters(tmp_data_dir):
    """3 キャラ × 異なる出現分布を持つ最小 novel.db を返す。

    page構成（10 page）:
      p1: なし
      p2: レティ
      p3: レティ, デューク
      p4: レティ, デューク
      p5: デューク, アストリッド
      p6: レティ, デューク, アストリッド
      p7: アストリッド
      p8: デューク
      p9: なし
      p10: なし

    char_count は p3=500, p4=300, p6=800, p2=p5=p7=p8=200, p1=p9=p10=100。
    => レティの登場: p2/p3/p4/p6 (4 回, first=2)
    => デュークの登場: p3/p4/p5/p6/p8 (5 回, first=3)
    => アストリッドの登場: p5/p6/p7 (3 回, first=5)
    """
    page_data = {
        1: (None, 100),
        2: ("レティ", 200),
        3: ("レティ, デューク", 500),
        4: ("レティ, デューク", 300),
        5: ("デューク, アストリッド", 200),
        6: ("レティ, デューク, アストリッド", 800),
        7: ("アストリッド", 200),
        8: ("デューク", 200),
        9: (None, 100),
        10: (None, 100),
    }
    upgrade_head()
    with with_db() as conn:
        cur = conn.execute(
            "INSERT INTO books (name, pdf_path, images_dir, page_count, indexed_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("test-book", "/x.pdf", "/imgs", 10),
        )
        book_id = cur.lastrowid
        for page_no, (mc, char_count) in page_data.items():
            conn.execute(
                "INSERT INTO pages "
                "(book_id, page_no, image_path, full_text, char_count, main_characters) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (book_id, page_no, None, f"page{page_no} body", char_count, mc),
            )
        conn.commit()
    return book_id


# ---------------------------------------------------------------------------
# list_book_characters_in_db
# ---------------------------------------------------------------------------

def test_list_characters_aggregates_and_sorts(db_with_characters):
    with with_db() as conn:
        stats = list_book_characters_in_db(conn, db_with_characters)
    # page_count 降順 → first_page 昇順 → name 昇順
    assert [s.name for s in stats] == ["デューク", "レティ", "アストリッド"]
    by_name = {s.name: s for s in stats}
    assert by_name["デューク"] == CharacterStat("デューク", first_page=3, page_count=5)
    assert by_name["レティ"] == CharacterStat("レティ", first_page=2, page_count=4)
    assert by_name["アストリッド"] == CharacterStat("アストリッド", first_page=5, page_count=3)


def test_list_characters_returns_empty_for_book_without_extractions(tmp_data_dir):
    upgrade_head()
    with with_db() as conn:
        cur = conn.execute(
            "INSERT INTO books (name, pdf_path, images_dir, page_count, indexed_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("empty-book", "/x.pdf", "/imgs", 3),
        )
        bid = cur.lastrowid
        for pn in range(1, 4):
            conn.execute(
                "INSERT INTO pages (book_id, page_no, image_path, full_text, char_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (bid, pn, None, "x", 1),
            )
        conn.commit()
    with with_db() as conn:
        assert list_book_characters_in_db(conn, bid) == []


# ---------------------------------------------------------------------------
# collect_character_pages
# ---------------------------------------------------------------------------

def test_collect_pages_returns_only_matching_pages(db_with_characters):
    with with_db() as conn:
        pages = collect_character_pages(conn, db_with_characters, "アストリッド")
    assert [p for p, _ in pages] == [5, 6, 7]


def test_collect_pages_exact_name_match(db_with_characters):
    """部分一致ではなく完全一致でフィルタする（'デュー' で 'デューク' を拾わない）。"""
    with with_db() as conn:
        pages = collect_character_pages(conn, db_with_characters, "デュー")
    assert pages == []


# ---------------------------------------------------------------------------
# top_scenes_for_character
# ---------------------------------------------------------------------------

def test_top_scenes_returns_pages_by_char_count_desc(db_with_characters):
    with with_db() as conn:
        scenes = top_scenes_for_character(conn, db_with_characters, "デューク", limit=3)
    # デュークの登場: p3=500, p4=300, p5=200, p6=800, p8=200
    # char_count 降順 top 3 → p6(800), p3(500), p4(300)
    assert [pn for pn, _ in scenes] == [6, 3, 4]


def test_top_scenes_respects_limit(db_with_characters):
    with with_db() as conn:
        scenes = top_scenes_for_character(
            conn, db_with_characters, "デューク", limit=2,
        )
    assert len(scenes) == 2


# ---------------------------------------------------------------------------
# upsert_character + list / get
# ---------------------------------------------------------------------------

def test_upsert_inserts_then_updates(db_with_characters):
    stat = CharacterStat("レティ", first_page=2, page_count=4)
    with with_db() as conn:
        upsert_character(conn, db_with_characters, stat, summary="初回サマリ")
    with with_db() as conn:
        row = get_character(conn, db_with_characters, "レティ")
    assert row is not None
    assert row.summary == "初回サマリ"
    assert row.generated_at is not None

    # 2 回目: summary=None でも統計値は更新、summary は前回を保持
    stat2 = CharacterStat("レティ", first_page=2, page_count=99)
    with with_db() as conn:
        upsert_character(conn, db_with_characters, stat2, summary=None)
    with with_db() as conn:
        row2 = get_character(conn, db_with_characters, "レティ")
    assert row2 is not None
    assert row2.page_count == 99
    assert row2.summary == "初回サマリ"  # 上書きされない

    # 3 回目: 新しい summary で上書き
    with with_db() as conn:
        upsert_character(conn, db_with_characters, stat2, summary="更新サマリ")
    with with_db() as conn:
        row3 = get_character(conn, db_with_characters, "レティ")
    assert row3 is not None
    assert row3.summary == "更新サマリ"


def test_list_characters_sorts_by_page_count(db_with_characters):
    """事前に 3 キャラ UPSERT してから list_characters を呼ぶ。"""
    for stat in [
        CharacterStat("レティ", 2, 4),
        CharacterStat("デューク", 3, 5),
        CharacterStat("アストリッド", 5, 3),
    ]:
        with with_db() as conn:
            upsert_character(conn, db_with_characters, stat, summary=None)
    with with_db() as conn:
        rows = list_characters(conn, db_with_characters)
    assert [r.name for r in rows] == ["デューク", "レティ", "アストリッド"]


# ---------------------------------------------------------------------------
# summarize_character
# ---------------------------------------------------------------------------

def test_summarize_character_calls_backend_with_book_and_name():
    pages = [(3, "本文ページ3"), (4, "本文ページ4")]
    with patch(
        "services.novel_db._llm_backend.QWEN_BACKEND.ask",
    ) as mock_ask:
        mock_ask.return_value = "  人物像です。  "
        out = summarize_character("テスト本", "レティ", pages)

    assert out == "人物像です。"
    assert mock_ask.call_count == 1
    prompt = mock_ask.call_args.args[0]
    assert "テスト本" in prompt
    assert "レティ" in prompt
    assert "page 3" in prompt
    assert "page 4" in prompt


def test_summarize_character_raises_for_empty_pages():
    with pytest.raises(ValueError, match="no pages"):
        summarize_character("book", "char", [])
