"""
services.pdf_service のユニットテスト。

PdfService.delete_pages / get_page_count を実際の PDF ファイルで検証する。

実行方法:
    cd backend
    uv run pytest tests/test_pdf_service.py -v
"""
import sys
import os

import pytest
import fitz

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.pdf_service import PdfService


def _make_pdf(path: str, page_count: int) -> None:
    """page_count ページ分の空白 PDF を生成する。"""
    doc = fitz.open()
    for i in range(page_count):
        page = doc.new_page()
        # 内容を入れて各ページが識別できるようにする（debug 用）
        page.insert_text((50, 50), f"Page {i + 1}")
    doc.save(path)
    doc.close()


# ---------------------------------------------------------------------------
# delete_pages
# ---------------------------------------------------------------------------

class TestDeletePages:
    def test_delete_single_page(self, tmp_path):
        pdf = tmp_path / "book.pdf"
        _make_pdf(str(pdf), 5)

        new_total = PdfService.delete_pages(str(pdf), [0])

        assert new_total == 4
        with fitz.open(str(pdf)) as doc:
            assert len(doc) == 4

    def test_delete_multiple_pages(self, tmp_path):
        pdf = tmp_path / "book.pdf"
        _make_pdf(str(pdf), 10)

        new_total = PdfService.delete_pages(str(pdf), [0, 2, 4])

        assert new_total == 7

    def test_delete_with_duplicate_indices(self, tmp_path):
        """重複インデックスは set で排除される。"""
        pdf = tmp_path / "book.pdf"
        _make_pdf(str(pdf), 5)

        new_total = PdfService.delete_pages(str(pdf), [1, 1, 1])

        assert new_total == 4

    def test_delete_with_unsorted_indices(self, tmp_path):
        """順不同のインデックスでも降順ソートで正しく処理される。"""
        pdf = tmp_path / "book.pdf"
        _make_pdf(str(pdf), 6)

        new_total = PdfService.delete_pages(str(pdf), [4, 0, 2])

        assert new_total == 3

    def test_delete_out_of_range_raises(self, tmp_path):
        pdf = tmp_path / "book.pdf"
        _make_pdf(str(pdf), 3)

        with pytest.raises(ValueError) as exc:
            PdfService.delete_pages(str(pdf), [5])
        assert "Invalid page index" in str(exc.value)

    def test_delete_negative_index_raises(self, tmp_path):
        pdf = tmp_path / "book.pdf"
        _make_pdf(str(pdf), 3)

        with pytest.raises(ValueError):
            PdfService.delete_pages(str(pdf), [-1])

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            PdfService.delete_pages(str(tmp_path / "nope.pdf"), [0])

    def test_temp_file_cleaned_up_on_error(self, tmp_path):
        """範囲外インデックスで失敗した場合 .tmp ファイルが残らない。"""
        pdf = tmp_path / "book.pdf"
        _make_pdf(str(pdf), 3)

        with pytest.raises(ValueError):
            PdfService.delete_pages(str(pdf), [10])

        # 元 PDF は無傷
        with fitz.open(str(pdf)) as doc:
            assert len(doc) == 3
        # .tmp ファイルは残っていない
        assert not (tmp_path / "book.pdf.tmp").exists()

    def test_delete_all_but_one_page(self, tmp_path):
        pdf = tmp_path / "book.pdf"
        _make_pdf(str(pdf), 3)

        new_total = PdfService.delete_pages(str(pdf), [0, 1])

        assert new_total == 1
