"""
services.thumbnail_service のユニットテスト。

PDF / WebP からサムネイル JPG を生成する純関数の挙動を確認する。

実行方法:
    cd backend
    uv run pytest tests/test_thumbnail_service.py -v
"""

import os
import sys

import fitz
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.thumbnail_service import ThumbnailService


def _make_pdf(path: str, page_count: int = 1, width: int = 400, height: int = 600) -> None:
    """指定サイズの PDF を生成する。"""
    doc = fitz.open()
    for _ in range(page_count):
        doc.new_page(width=width, height=height)
    doc.save(path)
    doc.close()


# ---------------------------------------------------------------------------
# generate_thumbnail
# ---------------------------------------------------------------------------


class TestGenerateThumbnail:
    def test_creates_jpg_from_pdf(self, tmp_path):
        pdf = tmp_path / "book.pdf"
        _make_pdf(str(pdf))
        thumb = tmp_path / "thumbs" / "book.jpg"

        result = ThumbnailService.generate_thumbnail(str(pdf), str(thumb))

        assert result is True
        assert thumb.exists()
        # JPEG として開ける
        with Image.open(str(thumb)) as img:
            assert img.format == "JPEG"

    def test_creates_parent_directory(self, tmp_path):
        """サムネイル親ディレクトリが存在しなくても自動作成される。"""
        pdf = tmp_path / "book.pdf"
        _make_pdf(str(pdf))
        thumb = tmp_path / "deep" / "nested" / "dir" / "book.jpg"

        result = ThumbnailService.generate_thumbnail(str(pdf), str(thumb))

        assert result is True
        assert thumb.exists()

    def test_zero_page_pdf_returns_false(self, tmp_path, monkeypatch):
        """ページ数 0 の PDF（fitz では作れないので mock）で False を返す。"""
        pdf = tmp_path / "empty.pdf"
        pdf.write_bytes(b"")  # ファイルだけ存在させる
        thumb = tmp_path / "empty.jpg"

        class _FakeDoc:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def __len__(self):
                return 0

        monkeypatch.setattr(
            "services.thumbnail_service.fitz.open",
            lambda _path: _FakeDoc(),
        )

        result = ThumbnailService.generate_thumbnail(str(pdf), str(thumb))

        assert result is False
        assert not thumb.exists()

    def test_missing_pdf_returns_false(self, tmp_path):
        """入力 PDF 不在で例外を投げず False を返す。"""
        thumb = tmp_path / "out.jpg"

        result = ThumbnailService.generate_thumbnail(str(tmp_path / "nope.pdf"), str(thumb))

        assert result is False

    def test_scale_affects_output_size(self, tmp_path):
        """scale パラメータが出力画像サイズに反映される。"""
        pdf = tmp_path / "book.pdf"
        _make_pdf(str(pdf), width=400, height=600)

        thumb_small = tmp_path / "small.jpg"
        thumb_large = tmp_path / "large.jpg"

        ThumbnailService.generate_thumbnail(str(pdf), str(thumb_small), scale=0.25)
        ThumbnailService.generate_thumbnail(str(pdf), str(thumb_large), scale=1.0)

        with Image.open(str(thumb_small)) as small, Image.open(str(thumb_large)) as large:
            # scale 1.0 の方が幅・高さともに大きい
            assert large.size[0] > small.size[0]
            assert large.size[1] > small.size[1]

    def test_default_scale_is_half(self, tmp_path):
        """デフォルト scale=0.5 で PDF サイズの半分程度になる。"""
        pdf = tmp_path / "book.pdf"
        _make_pdf(str(pdf), width=400, height=600)
        thumb = tmp_path / "book.jpg"

        ThumbnailService.generate_thumbnail(str(pdf), str(thumb))

        with Image.open(str(thumb)) as img:
            # PDF 幅 400 に対し scale 0.5 → 200 px
            assert img.size[0] == 200
            assert img.size[1] == 300

    def test_uses_first_page(self, tmp_path):
        """複数ページ PDF で 1 ページ目が使われる（例外なく成功するだけで OK）。"""
        pdf = tmp_path / "book.pdf"
        _make_pdf(str(pdf), page_count=5)
        thumb = tmp_path / "book.jpg"

        result = ThumbnailService.generate_thumbnail(str(pdf), str(thumb))

        assert result is True
        assert thumb.exists()
