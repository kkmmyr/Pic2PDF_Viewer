"""
utils.file_utils のユニットテスト。

ファイル種別判定のヘルパー関数を確認する。

実行方法:
    cd backend
    uv run pytest tests/test_file_utils.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.file_utils import is_image_file, is_pdf_file, is_webp_file, is_zip_file


class TestIsWebpFile:
    def test_lowercase(self):
        assert is_webp_file("image.webp") is True

    def test_uppercase(self):
        assert is_webp_file("IMAGE.WEBP") is True

    def test_mixed_case(self):
        assert is_webp_file("image.WebP") is True

    def test_other_extension(self):
        assert is_webp_file("image.jpg") is False

    def test_no_extension(self):
        assert is_webp_file("image") is False

    def test_partial_match(self):
        """webp を含むだけでは false（厳密な拡張子一致）。"""
        assert is_webp_file("webp.txt") is False

    def test_path_with_directory(self):
        assert is_webp_file("/path/to/image.webp") is True


class TestIsZipFile:
    def test_lowercase(self):
        assert is_zip_file("archive.zip") is True

    def test_uppercase(self):
        assert is_zip_file("ARCHIVE.ZIP") is True

    def test_other_extension(self):
        assert is_zip_file("archive.tar") is False

    def test_no_extension(self):
        assert is_zip_file("archive") is False


class TestIsImageFile:
    def test_webp(self):
        assert is_image_file("a.webp") is True

    def test_jpg(self):
        assert is_image_file("a.jpg") is True

    def test_jpeg(self):
        assert is_image_file("a.jpeg") is True

    def test_png(self):
        assert is_image_file("a.png") is True

    def test_uppercase(self):
        assert is_image_file("A.PNG") is True

    def test_pdf_excluded(self):
        assert is_image_file("a.pdf") is False

    def test_text_excluded(self):
        assert is_image_file("a.txt") is False


class TestIsPdfFile:
    def test_lowercase(self):
        assert is_pdf_file("book.pdf") is True

    def test_uppercase(self):
        assert is_pdf_file("BOOK.PDF") is True

    def test_strict_extension_match(self):
        """`.pdfx` のような誤ヒットを起こさない。"""
        assert is_pdf_file("book.pdfx") is False

    def test_partial_match_rejected(self):
        assert is_pdf_file("pdf.txt") is False
