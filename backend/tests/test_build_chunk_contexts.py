"""services/novel_db/contextualizer.should_skip_context の単体テスト。

B-9 改良 (2026-05-12): skip 判定境界を検証する。
Phase 55-2 (2026-05-14): スクリプトから contextualizer へ移動に伴い、
  importlib 経由の動的ロードを直接 import に置換。
"""

from services.novel_db.contextualizer import should_skip_context


def test_skip_when_char_count_below_min():
    """char_count < NOVEL_DB_MIN_BODY_CHARS (300) の chunk は skip。"""
    assert should_skip_context(100, page_no=50, page_count=200) is True
    assert should_skip_context(299, page_no=50, page_count=200) is True


def test_not_skip_at_min_boundary():
    """char_count == 300 はちょうど境界、skip しない。"""
    assert should_skip_context(300, page_no=50, page_count=200) is False


def test_not_skip_in_middle_pages():
    """十分な char_count + 中間ページ → skip しない。"""
    assert should_skip_context(500, page_no=50, page_count=200) is False


def test_skip_in_leading_margin():
    """先頭 NOVEL_DB_BODY_PAGE_MARGIN (5) ページ以内は skip。"""
    assert should_skip_context(500, page_no=1, page_count=200) is True
    assert should_skip_context(500, page_no=5, page_count=200) is True
    assert should_skip_context(500, page_no=6, page_count=200) is False


def test_skip_in_trailing_margin():
    """末尾 NOVEL_DB_BODY_PAGE_MARGIN ページ以内は skip。"""
    assert should_skip_context(500, page_no=200, page_count=200) is True
    assert should_skip_context(500, page_no=196, page_count=200) is True
    assert should_skip_context(500, page_no=195, page_count=200) is False
