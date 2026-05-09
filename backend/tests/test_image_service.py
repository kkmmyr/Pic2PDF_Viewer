"""
services.image_service のユニットテスト。

list_book_images / delete_book_image_pages を実際の WebP ファイルで検証する。
"""
import os
import sys

import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.image_service import delete_book_image_pages, list_book_images


def _make_webp(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = Image.new("RGB", (10, 10), (255, 0, 0))
    img.save(path, "WEBP")


def _populate_book(book_dir: str, count: int) -> None:
    """book_dir/ に N 枚の WebP を 01.webp, 02.webp, ... と作る。"""
    for i in range(count):
        _make_webp(os.path.join(book_dir, f"{i + 1:02d}.webp"))


# ---------------------------------------------------------------------------
# list_book_images
# ---------------------------------------------------------------------------

class TestListBookImages:
    def test_returns_empty_when_directory_missing(self, tmp_path):
        assert list_book_images(str(tmp_path), "nope") == []

    def test_natsort_order(self, tmp_path):
        book = tmp_path / "book"
        # 11.webp / 2.webp / 1.webp の順で作る → natsort で 1, 2, 11 の順を期待
        _make_webp(str(book / "11.webp"))
        _make_webp(str(book / "2.webp"))
        _make_webp(str(book / "1.webp"))

        result = list_book_images(str(tmp_path), "book")
        assert [os.path.basename(p) for p in result] == ["1.webp", "2.webp", "11.webp"]

    def test_only_webp_returned(self, tmp_path):
        book = tmp_path / "book"
        _make_webp(str(book / "01.webp"))
        # 別形式は無視される
        with open(book / "note.txt", "w") as f:
            f.write("dummy")

        result = list_book_images(str(tmp_path), "book")
        assert len(result) == 1
        assert result[0].endswith("01.webp")

    def test_with_path(self, tmp_path):
        nested = tmp_path / "subdir" / "book"
        _make_webp(str(nested / "01.webp"))

        result = list_book_images(str(tmp_path), "book", "subdir")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# delete_book_image_pages
# ---------------------------------------------------------------------------

class TestDeleteBookImagePages:
    def test_delete_single_page(self, tmp_path):
        book = tmp_path / "book"
        _populate_book(str(book), 5)

        new_total = delete_book_image_pages(str(book), [0])
        assert new_total == 4
        # 01.webp が消えて 02..05 が残る
        assert sorted(os.listdir(book)) == ["02.webp", "03.webp", "04.webp", "05.webp"]

    def test_delete_multiple_pages_descending_order(self, tmp_path):
        """インデックスずれ防止のため降順削除されることの暗黙的検証。
        0, 2, 4 を指定 → 01.webp, 03.webp, 05.webp が消える。
        """
        book = tmp_path / "book"
        _populate_book(str(book), 5)

        new_total = delete_book_image_pages(str(book), [0, 2, 4])
        assert new_total == 2
        assert sorted(os.listdir(book)) == ["02.webp", "04.webp"]

    def test_duplicate_indices_are_deduplicated(self, tmp_path):
        book = tmp_path / "book"
        _populate_book(str(book), 3)

        new_total = delete_book_image_pages(str(book), [1, 1, 1])
        assert new_total == 2

    def test_raises_when_directory_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            delete_book_image_pages(str(tmp_path / "nope"), [0])

    def test_raises_when_index_out_of_range(self, tmp_path):
        book = tmp_path / "book"
        _populate_book(str(book), 3)

        with pytest.raises(ValueError):
            delete_book_image_pages(str(book), [99])

    def test_raises_when_negative_index(self, tmp_path):
        book = tmp_path / "book"
        _populate_book(str(book), 3)

        with pytest.raises(ValueError):
            delete_book_image_pages(str(book), [-1])
