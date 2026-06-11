"""
utils.file_naming のユニットテスト。

PDF→サムネイル名の変換ロジックを確認する。

実行方法:
    cd backend
    uv run pytest tests/test_file_naming.py -v
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.file_naming import get_thumbnail_name


class TestGetThumbnailName:
    def test_pdf_to_jpg(self):
        assert get_thumbnail_name("book.pdf") == "book.jpg"

    def test_uppercase_pdf_extension(self):
        # os.path.splitext は大文字を保持する
        assert get_thumbnail_name("book.PDF") == "book.jpg"

    def test_no_extension(self):
        assert get_thumbnail_name("book") == "book.jpg"

    def test_multi_dot_filename(self):
        """`a.b.pdf` → `a.b.jpg`（splitext は最後のドットだけを分離）。"""
        assert get_thumbnail_name("a.b.pdf") == "a.b.jpg"

    def test_japanese_filename(self):
        assert get_thumbnail_name("漫画.pdf") == "漫画.jpg"

    def test_with_spaces(self):
        assert get_thumbnail_name("My Book.pdf") == "My Book.jpg"

    def test_already_jpg_input(self):
        """jpg 入力でも .jpg 拡張子で返る。"""
        assert get_thumbnail_name("book.jpg") == "book.jpg"
