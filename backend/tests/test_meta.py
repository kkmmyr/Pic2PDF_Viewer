"""
services.meta_store / services.auto_fill_service のユニットテスト。

実行方法:
    cd backend
    uv run pytest tests/test_meta.py -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.meta_store import make_key
from services.auto_fill_service import _is_missing, _is_unknown


class TestMakeKey:
    def test_with_path(self):
        assert make_key("sub/dir", "book.pdf") == "sub/dir/book.pdf"

    def test_empty_path(self):
        assert make_key("", "book.pdf") == "book.pdf"

    def test_nested_path(self):
        assert make_key("a/b/c", "x.pdf") == "a/b/c/x.pdf"


class TestIsMissing:
    def test_key_not_in_meta(self):
        assert _is_missing({}, "missing.pdf") is True

    def test_empty_authors(self):
        meta = {"book.pdf": {"authors": []}}
        assert _is_missing(meta, "book.pdf") is True

    def test_with_real_author(self):
        meta = {"book.pdf": {"authors": ["サークルA"]}}
        assert _is_missing(meta, "book.pdf") is False

    def test_unknown_author_not_missing(self):
        # 「作者不明」は登録済みなので missing ではない
        meta = {"book.pdf": {"authors": ["作者不明"]}}
        assert _is_missing(meta, "book.pdf") is False


class TestIsUnknown:
    def test_unknown_author(self):
        meta = {"book.pdf": {"authors": ["作者不明"]}}
        assert _is_unknown(meta, "book.pdf") is True

    def test_real_author_not_unknown(self):
        meta = {"book.pdf": {"authors": ["サークルA"]}}
        assert _is_unknown(meta, "book.pdf") is False

    def test_empty_authors_not_unknown(self):
        meta = {"book.pdf": {"authors": []}}
        assert _is_unknown(meta, "book.pdf") is False

    def test_key_not_in_meta(self):
        assert _is_unknown({}, "missing.pdf") is False

    def test_multiple_authors_with_unknown(self):
        # ["作者不明", "Author2"] は完全一致しないので unknown ではない
        meta = {"book.pdf": {"authors": ["作者不明", "Author2"]}}
        assert _is_unknown(meta, "book.pdf") is False
