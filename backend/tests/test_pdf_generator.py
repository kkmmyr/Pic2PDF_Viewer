"""
services.pdf_generator のユニットテスト。

実 PDF 出力の中身までは検証せず、ファイルの存在・移動・サムネイル生成・
画像収集ロジックなど、回帰の起きやすい挙動に絞って確認する。

実行方法:
    cd backend
    uv run pytest tests/test_pdf_generator.py -v
"""

import os
import sys
import zipfile
from io import BytesIO

import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.pdf_generator import _check_zip_safety, _collect_images, scan_and_generate

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _make_webp(path: str, color: tuple = (255, 0, 0)) -> None:
    """単色の WebP 画像を作成する。"""
    img = Image.new("RGB", (100, 150), color)
    img.save(path, "WEBP")


def _make_zip_of_webps(zip_path: str, names: list[str]) -> None:
    """WebP を含む ZIP を作る。"""
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name in names:
            buf = BytesIO()
            Image.new("RGB", (100, 150), (0, 128, 0)).save(buf, "WEBP")
            zf.writestr(name, buf.getvalue())


# ---------------------------------------------------------------------------
# _collect_images
# ---------------------------------------------------------------------------


class TestCollectImages:
    def test_collects_only_webp(self, tmp_path):
        _make_webp(str(tmp_path / "a.webp"))
        _make_webp(str(tmp_path / "b.webp"))
        (tmp_path / "readme.txt").write_text("hello")
        (tmp_path / "thumb.jpg").write_bytes(b"fake")

        result = _collect_images(str(tmp_path))
        assert len(result) == 2
        assert all(p.endswith(".webp") for p in result)

    def test_natural_sort(self, tmp_path):
        # 自然順ソート: 1, 2, 10 の順になることを確認（辞書順では 1, 10, 2）
        for i in [1, 2, 10]:
            _make_webp(str(tmp_path / f"{i}.webp"))

        result = _collect_images(str(tmp_path))
        names = [os.path.basename(p) for p in result]
        assert names == ["1.webp", "2.webp", "10.webp"]

    def test_empty_dir_returns_empty_list(self, tmp_path):
        assert _collect_images(str(tmp_path)) == []


# ---------------------------------------------------------------------------
# _check_zip_safety — zip bomb 対策
# ---------------------------------------------------------------------------


class TestCheckZipSafety:
    """_check_zip_safety は ZIP 内の WebP エントリ数・サイズが上限を
    超えたら ValueError を投げる。process_zip の except 節に集約され、
    ジョブの failed_items に記録される。"""

    def _make_info(self, name: str, size: int) -> zipfile.ZipInfo:
        info = zipfile.ZipInfo(filename=name)
        info.file_size = size
        return info

    def test_normal_size_passes(self):
        infos = [self._make_info(f"{i}.webp", 1024) for i in range(10)]
        # 例外なく通る
        _check_zip_safety(infos, "ok.zip")

    def test_too_many_entries_raises(self, monkeypatch):
        from services import pdf_generator as pg

        monkeypatch.setattr(pg, "ZIP_MAX_ENTRIES", 5)
        infos = [self._make_info(f"{i}.webp", 100) for i in range(6)]
        with pytest.raises(ValueError, match="entry count"):
            _check_zip_safety(infos, "many.zip")

    def test_per_file_limit_raises(self, monkeypatch):
        from services import pdf_generator as pg

        monkeypatch.setattr(pg, "ZIP_MAX_PER_FILE_BYTES", 1024)
        infos = [self._make_info("big.webp", 2048)]
        with pytest.raises(ValueError, match="per-file limit"):
            _check_zip_safety(infos, "big.zip")

    def test_total_size_limit_raises(self, monkeypatch):
        from services import pdf_generator as pg

        monkeypatch.setattr(pg, "ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES", 5000)
        # 各 1500 バイト × 4 件 = 6000 バイト > 5000
        infos = [self._make_info(f"{i}.webp", 1500) for i in range(4)]
        with pytest.raises(ValueError, match="total uncompressed"):
            _check_zip_safety(infos, "total.zip")


# ---------------------------------------------------------------------------
# scan_and_generate — フォルダ → PDF 変換
# ---------------------------------------------------------------------------


@pytest.fixture
def gen_env(tmp_path):
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "pdfs"
    thumb_dir = tmp_path / "thumbnails"
    images_dir = tmp_path / "images"
    complete_dir = tmp_path / "complete"
    for d in (source_dir, output_dir, thumb_dir, images_dir, complete_dir):
        d.mkdir()
    return {
        "source": source_dir,
        "output": output_dir,
        "thumb": thumb_dir,
        "images": images_dir,
        "complete": complete_dir,
    }


class TestScanAndGenerate:
    def test_directory_to_pdf(self, gen_env):
        # source/book1/ に WebP を 2 枚配置
        book_dir = gen_env["source"] / "book1"
        book_dir.mkdir()
        _make_webp(str(book_dir / "1.webp"))
        _make_webp(str(book_dir / "2.webp"))

        result = scan_and_generate(
            str(gen_env["source"]),
            str(gen_env["output"]),
            str(gen_env["thumb"]),
            str(gen_env["images"]),
            str(gen_env["complete"]),
        )

        assert "book1.pdf" in result.generated
        assert result.failed_items == []
        assert (gen_env["output"] / "book1.pdf").exists()
        assert (gen_env["thumb"] / "book1.jpg").exists()
        # 元フォルダは complete/ に移動されている
        assert (gen_env["complete"] / "book1").exists()
        assert not book_dir.exists()

    def test_zip_to_pdf(self, gen_env):
        # source/comic.zip を作成
        zip_path = gen_env["source"] / "comic.zip"
        _make_zip_of_webps(str(zip_path), ["1.webp", "2.webp"])

        result = scan_and_generate(
            str(gen_env["source"]),
            str(gen_env["output"]),
            str(gen_env["thumb"]),
            str(gen_env["images"]),
            str(gen_env["complete"]),
        )

        assert "comic.pdf" in result.generated
        assert result.failed_items == []
        assert (gen_env["output"] / "comic.pdf").exists()
        # ZIP は complete/ に移動されている
        assert (gen_env["complete"] / "comic.zip").exists()
        assert not zip_path.exists()

    def test_progress_callback_invoked(self, gen_env):
        book_dir = gen_env["source"] / "callback_book"
        book_dir.mkdir()
        _make_webp(str(book_dir / "1.webp"))

        called = []
        scan_and_generate(
            str(gen_env["source"]),
            str(gen_env["output"]),
            str(gen_env["thumb"]),
            str(gen_env["images"]),
            str(gen_env["complete"]),
            progress_callback=called.append,
        )
        assert "callback_book" in called

    def test_no_webp_no_pdf(self, gen_env):
        # source/ に WebP/ZIP がなければ PDF は生成されない
        (gen_env["source"] / "ignored.txt").write_text("hi")

        result = scan_and_generate(
            str(gen_env["source"]),
            str(gen_env["output"]),
            str(gen_env["thumb"]),
            str(gen_env["images"]),
            str(gen_env["complete"]),
        )
        assert result.generated == []
        assert result.failed_items == []

    # 回帰テスト: image-only モード (output_dir=None) でも complete/ への移動が発生する
    # 過去バグ: pdfs_compressed/ 削除後、process_zip/process_directory の except に
    # 例外が吸収され self.moves が空のまま、complete/ への移動が起きなかった。
    def test_image_only_mode_zip_moves_to_complete(self, gen_env):
        zip_path = gen_env["source"] / "comic.zip"
        _make_zip_of_webps(str(zip_path), ["1.webp", "2.webp"])

        result = scan_and_generate(
            str(gen_env["source"]),
            None,  # ← image-only モード
            str(gen_env["thumb"]),
            str(gen_env["images"]),
            str(gen_env["complete"]),
        )

        assert "comic.pdf" in result.generated
        assert result.failed_items == []
        # PDF は生成されない
        assert not (gen_env["output"] / "comic.pdf").exists()
        # サムネイル / images / complete 移動はすべて発生する
        assert (gen_env["thumb"] / "comic.jpg").exists()
        assert (gen_env["images"] / "comic").is_dir()
        assert (gen_env["complete"] / "comic.zip").exists()
        assert not zip_path.exists()

    def test_image_only_mode_directory_moves_to_complete(self, gen_env):
        book_dir = gen_env["source"] / "book1"
        book_dir.mkdir()
        _make_webp(str(book_dir / "1.webp"))

        result = scan_and_generate(
            str(gen_env["source"]),
            None,
            str(gen_env["thumb"]),
            str(gen_env["images"]),
            str(gen_env["complete"]),
        )

        assert "book1.pdf" in result.generated
        assert result.failed_items == []
        assert not (gen_env["output"] / "book1.pdf").exists()
        assert (gen_env["complete"] / "book1").exists()
        assert not book_dir.exists()

    # 回帰テスト: 個別書籍の失敗が failed_items に集約され、サイレント失敗にならない
    def test_failure_is_recorded_in_failed_items(self, gen_env):
        # 不正な ZIP（中身が壊れている）→ ZipFile 展開で例外
        bad_zip = gen_env["source"] / "broken.zip"
        bad_zip.write_bytes(b"not a real zip file")
        # 正常な ZIP も同時に処理される
        good_zip = gen_env["source"] / "good.zip"
        _make_zip_of_webps(str(good_zip), ["1.webp"])

        result = scan_and_generate(
            str(gen_env["source"]),
            None,
            str(gen_env["thumb"]),
            str(gen_env["images"]),
            str(gen_env["complete"]),
        )

        # 正常分は生成、失敗分は failed_items に記録される（黙殺されない）
        assert "good.pdf" in result.generated
        assert len(result.failed_items) == 1
        assert result.failed_items[0][0] == "broken"
        assert isinstance(result.failed_items[0][1], str) and result.failed_items[0][1]
        # 失敗した ZIP は complete/ には移動しない（元のまま）
        assert bad_zip.exists()
        assert (gen_env["complete"] / "good.zip").exists()
