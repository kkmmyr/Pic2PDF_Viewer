"""
services.image_service のユニットテスト。

list_book_images / delete_book_image_pages を実際の WebP ファイルで検証する。
"""
import os
import sys

import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.image_service import (
    delete_book_image_pages,
    list_book_images,
    reorder_book_image_pages,
)


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


# ---------------------------------------------------------------------------
# reorder_book_image_pages
# ---------------------------------------------------------------------------

def _populate_with_distinct_colors(book_dir: str, count: int) -> list[tuple[int, int, int]]:
    """N 枚の WebP を異なる色で作って色リストを返す（順序検証用）。"""
    colors = [(i * 30 % 256, (i * 50) % 256, (i * 70) % 256) for i in range(count)]
    for i, c in enumerate(colors):
        _make_webp_with_color(os.path.join(book_dir, f"{i + 1:02d}.webp"), c)
    return colors


def _make_webp_with_color(path: str, color: tuple[int, int, int]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # lossless=True にしないと WebP のデフォルトの非可逆圧縮で色が微妙にずれる
    Image.new("RGB", (10, 10), color).save(path, "WEBP", lossless=True)


def _read_color_at(path: str) -> tuple[int, int, int]:
    return Image.open(path).convert("RGB").getpixel((0, 0))


class TestReorderBookImagePages:
    def test_reorder_swap_first_and_last(self, tmp_path):
        book = tmp_path / "book"
        colors = _populate_with_distinct_colors(str(book), 5)
        # 4,1,2,3,0 に並び替え
        new_total = reorder_book_image_pages(str(book), [4, 1, 2, 3, 0])
        assert new_total == 5

        # ファイル名は page_0001..page_0005.webp になる
        assert sorted(os.listdir(book)) == [f"page_{i:04d}.webp" for i in range(1, 6)]
        # 新先頭は元の最終（color[4]）
        assert _read_color_at(str(book / "page_0001.webp")) == colors[4]
        # 新末尾は元の先頭（color[0]）
        assert _read_color_at(str(book / "page_0005.webp")) == colors[0]
        # 中央は色がそのまま
        assert _read_color_at(str(book / "page_0002.webp")) == colors[1]

    def test_reorder_identity_renames_files(self, tmp_path):
        """identity を渡しても全ファイルが page_NNNN.webp 形式に揃う。"""
        book = tmp_path / "book"
        _populate_book(str(book), 3)
        new_total = reorder_book_image_pages(str(book), [0, 1, 2])
        assert new_total == 3
        assert sorted(os.listdir(book)) == ["page_0001.webp", "page_0002.webp", "page_0003.webp"]

    def test_reorder_full_reverse(self, tmp_path):
        book = tmp_path / "book"
        colors = _populate_with_distinct_colors(str(book), 4)
        reorder_book_image_pages(str(book), [3, 2, 1, 0])
        assert _read_color_at(str(book / "page_0001.webp")) == colors[3]
        assert _read_color_at(str(book / "page_0004.webp")) == colors[0]

    def test_reorder_rejects_duplicate(self, tmp_path):
        book = tmp_path / "book"
        _populate_book(str(book), 3)
        with pytest.raises(ValueError):
            reorder_book_image_pages(str(book), [0, 0, 1])

    def test_reorder_rejects_missing_index(self, tmp_path):
        book = tmp_path / "book"
        _populate_book(str(book), 3)
        with pytest.raises(ValueError):
            reorder_book_image_pages(str(book), [0, 1])  # 2 が欠落

    def test_reorder_rejects_out_of_range(self, tmp_path):
        book = tmp_path / "book"
        _populate_book(str(book), 3)
        with pytest.raises(ValueError):
            reorder_book_image_pages(str(book), [0, 1, 99])

    def test_reorder_raises_when_directory_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            reorder_book_image_pages(str(tmp_path / "nope"), [0])

    def test_reorder_handles_collision_with_existing_names(self, tmp_path):
        """初期ファイル名と新採番が衝突するケース（既存に page_0001.webp があっても OK）。"""
        book = tmp_path / "book"
        # 既に page_NNNN.webp 形式の名前で作成
        _make_webp_with_color(str(book / "page_0001.webp"), (255, 0, 0))
        _make_webp_with_color(str(book / "page_0002.webp"), (0, 255, 0))
        _make_webp_with_color(str(book / "page_0003.webp"), (0, 0, 255))
        # 逆順に並び替え
        reorder_book_image_pages(str(book), [2, 1, 0])
        # 新先頭は元 page_0003 = 青
        assert _read_color_at(str(book / "page_0001.webp")) == (0, 0, 255)
        assert _read_color_at(str(book / "page_0003.webp")) == (255, 0, 0)
