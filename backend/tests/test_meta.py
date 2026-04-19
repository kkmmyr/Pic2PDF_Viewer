"""
services.meta_store / services.auto_fill_service のユニットテスト。

実行方法:
    cd backend
    pytest tests/test_meta.py -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.meta_store import make_key
from services.auto_fill_service import _has_real_author


class TestMakeKey:
    def test_with_path(self):
        assert make_key("sub/dir", "book.pdf") == "sub/dir/book.pdf"

    def test_empty_path(self):
        assert make_key("", "book.pdf") == "book.pdf"

    def test_nested_path(self):
        assert make_key("a/b/c", "x.pdf") == "a/b/c/x.pdf"


class TestHasRealAuthor:
    def test_real_author(self):
        meta = {"book.pdf": {"authors": ["サークルA"]}}
        assert _has_real_author(meta, "book.pdf") is True

    def test_unknown_author(self):
        meta = {"book.pdf": {"authors": ["作者不明"]}}
        assert _has_real_author(meta, "book.pdf") is False

    def test_empty_authors(self):
        meta = {"book.pdf": {"authors": []}}
        assert _has_real_author(meta, "book.pdf") is False

    def test_key_not_in_meta(self):
        assert _has_real_author({}, "missing.pdf") is False

    def test_multiple_authors_with_unknown(self):
        # 複数著者の場合は ["作者不明"] と完全一致でないため True
        meta = {"book.pdf": {"authors": ["作者不明", "Author2"]}}
        assert _has_real_author(meta, "book.pdf") is True
