"""
services.pdf_generator のユニットテスト。

実 PDF 出力の中身までは検証せず、ファイルの存在・移動・サムネイル生成・
画像収集ロジックなど、回帰の起きやすい挙動に絞って確認する。

実行方法:
    cd backend
    uv run pytest tests/test_pdf_generator.py -v
"""
import sys
import os
import zipfile
from io import BytesIO

import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.pdf_generator import _collect_images, scan_and_generate, batch_compress


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
# scan_and_generate — フォルダ → PDF 変換
# ---------------------------------------------------------------------------

@pytest.fixture
def gen_env(tmp_path):
    source_dir   = tmp_path / "source"
    output_dir   = tmp_path / "pdfs"
    thumb_dir    = tmp_path / "thumbnails"
    images_dir   = tmp_path / "images"
    complete_dir = tmp_path / "complete"
    for d in (source_dir, output_dir, thumb_dir, images_dir, complete_dir):
        d.mkdir()
    return {
        "source": source_dir, "output": output_dir, "thumb": thumb_dir,
        "images": images_dir, "complete": complete_dir,
    }


class TestScanAndGenerate:
    def test_directory_to_pdf(self, gen_env):
        # source/book1/ に WebP を 2 枚配置
        book_dir = gen_env["source"] / "book1"
        book_dir.mkdir()
        _make_webp(str(book_dir / "1.webp"))
        _make_webp(str(book_dir / "2.webp"))

        result = scan_and_generate(
            str(gen_env["source"]), str(gen_env["output"]), str(gen_env["thumb"]),
            str(gen_env["images"]), str(gen_env["complete"]),
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
            str(gen_env["source"]), str(gen_env["output"]), str(gen_env["thumb"]),
            str(gen_env["images"]), str(gen_env["complete"]),
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
            str(gen_env["source"]), str(gen_env["output"]), str(gen_env["thumb"]),
            str(gen_env["images"]), str(gen_env["complete"]),
            progress_callback=called.append,
        )
        assert "callback_book" in called

    def test_no_webp_no_pdf(self, gen_env):
        # source/ に WebP/ZIP がなければ PDF は生成されない
        (gen_env["source"] / "ignored.txt").write_text("hi")

        result = scan_and_generate(
            str(gen_env["source"]), str(gen_env["output"]), str(gen_env["thumb"]),
            str(gen_env["images"]), str(gen_env["complete"]),
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
            str(gen_env["source"]), None,  # ← image-only モード
            str(gen_env["thumb"]), str(gen_env["images"]), str(gen_env["complete"]),
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
            str(gen_env["source"]), None,
            str(gen_env["thumb"]), str(gen_env["images"]), str(gen_env["complete"]),
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
            str(gen_env["source"]), None,
            str(gen_env["thumb"]), str(gen_env["images"]), str(gen_env["complete"]),
        )

        # 正常分は生成、失敗分は failed_items に記録される（黙殺されない）
        assert "good.pdf" in result.generated
        assert len(result.failed_items) == 1
        assert result.failed_items[0][0] == "broken"
        assert isinstance(result.failed_items[0][1], str) and result.failed_items[0][1]
        # 失敗した ZIP は complete/ には移動しない（元のまま）
        assert bad_zip.exists()
        assert (gen_env["complete"] / "good.zip").exists()


# ---------------------------------------------------------------------------
# batch_compress
# ---------------------------------------------------------------------------

class TestBatchCompress:
    """
    batch_compress は images_dir 配下の **各サブフォルダ** を走査し、
    そのフォルダ名で PDF を生成して **親ディレクトリ相当** に出力する。

    例: images_dir/alpha/*.webp → output_dir/alpha.pdf
        images_dir/sub1/alpha/*.webp → output_dir/sub1/alpha.pdf
    """
    def test_compresses_each_subfolder(self, tmp_path):
        images_dir = tmp_path / "images"
        out_dir = tmp_path / "compressed"
        images_dir.mkdir()
        out_dir.mkdir()

        for name in ("alpha", "beta"):
            sub = images_dir / name
            sub.mkdir()
            _make_webp(str(sub / "1.webp"))

        generated = batch_compress(str(images_dir), str(out_dir), quality=50)

        # フォルダは images_dir 直下なので出力は out_dir 直下
        assert sorted(generated) == [
            os.path.join("alpha", "alpha.pdf"),
            os.path.join("beta", "beta.pdf"),
        ]
        assert (out_dir / "alpha.pdf").exists()
        assert (out_dir / "beta.pdf").exists()

    def test_skips_already_compressed(self, tmp_path):
        images_dir = tmp_path / "images"
        out_dir = tmp_path / "compressed"
        images_dir.mkdir()
        out_dir.mkdir()

        sub = images_dir / "alpha"
        sub.mkdir()
        _make_webp(str(sub / "1.webp"))

        # 既に出力先に PDF が存在する状態にする（出力は out_dir 直下）
        (out_dir / "alpha.pdf").write_bytes(b"existing")

        generated = batch_compress(str(images_dir), str(out_dir), quality=50)
        assert generated == []
        # 既存ファイルは上書きされない
        assert (out_dir / "alpha.pdf").read_bytes() == b"existing"

    def test_progress_callback_receives_relative_path(self, tmp_path):
        images_dir = tmp_path / "images"
        out_dir = tmp_path / "compressed"
        images_dir.mkdir()
        out_dir.mkdir()

        sub = images_dir / "alpha"
        sub.mkdir()
        _make_webp(str(sub / "1.webp"))

        called: list[str] = []
        batch_compress(str(images_dir), str(out_dir), quality=50, progress_callback=called.append)

        assert any("alpha" in c for c in called)
