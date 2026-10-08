"""services/novel_db/llm.py:build_prompt の単体テスト。

書籍俯瞰サマリの埋め込み（B-5）と、scope ごとのヘッダ生成を確認する。
"""

from services.novel_db.prompt_builder import build_prompt
from services.novel_db.search import Scope, SearchHit


def _hit(book: str, page: int, *, snippet: str = "本文", chars: list[str] | None = None) -> SearchHit:
    return SearchHit(
        book_name=book,
        page_no=page,
        snippet=snippet,
        has_highlight=False,
        image_url=None,
        rrf_score=0.5,
        main_characters=chars or [],
    )


# ---------------------------------------------------------------------------
# scope ごとの基本構造
# ---------------------------------------------------------------------------


def test_book_scope_omits_book_name_in_page_header():
    hits = [_hit("book-1", 50, snippet="セリフ")]
    prompt = build_prompt("質問は？", hits, Scope("book", "book-1"))
    assert "[page 50]" in prompt
    assert "book-1 page 50" not in prompt
    assert "質問: 質問は？" in prompt


def test_all_scope_includes_book_name_in_page_header():
    hits = [_hit("book-1", 50)]
    prompt = build_prompt("質問は？", hits, Scope("all"))
    assert "[book-1 page 50]" in prompt


def test_main_characters_hint_is_included():
    hits = [_hit("book-1", 50, chars=["レティ", "デューク"])]
    prompt = build_prompt("質問は？", hits, Scope("book", "book-1"))
    assert "主要登場人物: レティ, デューク" in prompt


# ---------------------------------------------------------------------------
# 書籍俯瞰サマリ（B-5）
# ---------------------------------------------------------------------------


def test_book_summaries_block_added_for_all_scope():
    hits = [_hit("book-1", 50)]
    prompt = build_prompt(
        "質問",
        hits,
        Scope("all"),
        book_summaries={"book-1": "あらすじ A", "book-2": "あらすじ B"},
    )
    assert "【書籍俯瞰サマリ】" in prompt
    assert "あらすじ A" in prompt
    assert "あらすじ B" in prompt
    # 書名が辞書順に並ぶ
    a_pos = prompt.index("あらすじ A")
    b_pos = prompt.index("あらすじ B")
    assert a_pos < b_pos


def test_book_summaries_block_added_for_series_scope():
    prompt = build_prompt(
        "質問",
        [_hit("book-1", 50)],
        Scope("series", "シリーズ X"),
        book_summaries={"book-1": "あらすじ"},
    )
    assert "【書籍俯瞰サマリ】" in prompt


def test_book_summaries_block_skipped_for_book_scope():
    """単冊スコープではサマリブロックは付与しない（page 抜粋で十分）。"""
    prompt = build_prompt(
        "質問",
        [_hit("book-1", 50)],
        Scope("book", "book-1"),
        book_summaries={"book-1": "あらすじ"},
    )
    assert "【書籍俯瞰サマリ】" not in prompt


def test_no_summaries_block_when_dict_is_empty_or_none():
    p1 = build_prompt("Q", [_hit("a", 1)], Scope("all"))
    p2 = build_prompt("Q", [_hit("a", 1)], Scope("all"), book_summaries=None)
    p3 = build_prompt("Q", [_hit("a", 1)], Scope("all"), book_summaries={})
    for p in (p1, p2, p3):
        assert "【書籍俯瞰サマリ】" not in p


def test_summaries_appear_before_context():
    """プロンプト内でサマリブロックは page 抜粋より前に出る。"""
    prompt = build_prompt(
        "質問",
        [_hit("book-1", 50)],
        Scope("all"),
        book_summaries={"book-1": "あらすじ"},
    )
    summary_pos = prompt.index("【書籍俯瞰サマリ】")
    page_pos = prompt.index("[book-1 page 50]")
    assert summary_pos < page_pos


def test_canonical_markup_is_preserved_in_qa_and_chat():
    from services.novel_db.prompt_builder import build_chat_context_block

    text = "本文の<mark>文字列</mark>と<ruby>原文</ruby>"
    hits = [_hit("book-1", 50, snippet=text)]
    assert text in build_prompt("質問", hits, Scope("book", "book-1"))
    assert text in build_chat_context_block(hits, Scope("book", "book-1"))


def test_search_highlights_are_removed_only_for_display_snippets():
    from services.novel_db.prompt_builder import build_chat_context_block

    hit = _hit("book-1", 50, snippet="検索<mark>表示</mark>")
    hit.has_highlight = True
    assert "検索表示" in build_prompt("質問", [hit], Scope("book", "book-1"))
    assert "検索表示" in build_chat_context_block([hit], Scope("book", "book-1"))
