"""
services.file_manager のユニットテスト。

実行方法:
    cd backend
    pytest tests/test_file_manager.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.file_manager import FileManager


def _make_dirs(tmp_path):
    """テスト用ディレクトリ構造を作成し dirs 辞書を返す。"""
    pdf_dir = tmp_path / "pdfs"
    thumb_dir = tmp_path / "thumbs"
    img_dir = tmp_path / "images"
    for d in (pdf_dir, thumb_dir, img_dir):
        d.mkdir()
    return {"pdf": str(pdf_dir), "thumb": str(thumb_dir), "img": str(img_dir)}


class TestRenameWithAssets:
    def test_rename_pdf_success(self, tmp_path):
        dirs = _make_dirs(tmp_path)
        open(os.path.join(dirs["pdf"], "old.pdf"), "w").close()

        FileManager.rename_with_assets("", "old.pdf", "new.pdf", False, dirs)

        assert os.path.exists(os.path.join(dirs["pdf"], "new.pdf"))
        assert not os.path.exists(os.path.join(dirs["pdf"], "old.pdf"))

    def test_rename_raises_if_src_not_found(self, tmp_path):
        dirs = _make_dirs(tmp_path)
        with pytest.raises(FileNotFoundError):
            FileManager.rename_with_assets("", "missing.pdf", "new.pdf", False, dirs)

    def test_rename_raises_if_dst_exists(self, tmp_path):
        dirs = _make_dirs(tmp_path)
        open(os.path.join(dirs["pdf"], "old.pdf"), "w").close()
        open(os.path.join(dirs["pdf"], "new.pdf"), "w").close()

        with pytest.raises(FileExistsError):
            FileManager.rename_with_assets("", "old.pdf", "new.pdf", False, dirs)

    def test_rename_folder_renames_thumbnail_and_images(self, tmp_path):
        dirs = _make_dirs(tmp_path)
        for d in (dirs["pdf"], dirs["thumb"], dirs["img"]):
            os.makedirs(os.path.join(d, "oldname"))

        FileManager.rename_with_assets("", "oldname", "newname", True, dirs)

        for d in (dirs["pdf"], dirs["thumb"], dirs["img"]):
            assert os.path.exists(os.path.join(d, "newname"))
            assert not os.path.exists(os.path.join(d, "oldname"))

    def test_rename_pdf_renames_thumbnail_and_images_dir(self, tmp_path):
        """PDF リネーム時にサムネイル (.jpg) と images サブディレクトリも追従する。"""
        dirs = _make_dirs(tmp_path)
        open(os.path.join(dirs["pdf"], "old.pdf"), "w").close()
        open(os.path.join(dirs["thumb"], "old.jpg"), "w").close()
        os.makedirs(os.path.join(dirs["img"], "old"))

        FileManager.rename_with_assets("", "old.pdf", "new.pdf", False, dirs)

        assert os.path.exists(os.path.join(dirs["pdf"], "new.pdf"))
        assert os.path.exists(os.path.join(dirs["thumb"], "new.jpg"))
        assert os.path.exists(os.path.join(dirs["img"], "new"))
        assert not os.path.exists(os.path.join(dirs["thumb"], "old.jpg"))
        assert not os.path.exists(os.path.join(dirs["img"], "old"))

    def test_rename_image_only_mode_succeeds_without_pdf(self, tmp_path):
        """PDF 不在でも images ディレクトリがあればリネーム成功（image-only モード）。"""
        dirs = _make_dirs(tmp_path)
        os.makedirs(os.path.join(dirs["img"], "old"))

        FileManager.rename_with_assets("", "old.pdf", "new.pdf", False, dirs)

        assert os.path.exists(os.path.join(dirs["img"], "new"))
        assert not os.path.exists(os.path.join(dirs["img"], "old"))

    def test_rename_rollback_on_failure(self, tmp_path, monkeypatch):
        """フォルダリネーム途中で失敗するとロールバックで元の状態に戻る。"""
        dirs = _make_dirs(tmp_path)
        # PDF + thumb + images の3点セット
        os.makedirs(os.path.join(dirs["pdf"], "src"))
        os.makedirs(os.path.join(dirs["thumb"], "src"))
        os.makedirs(os.path.join(dirs["img"], "src"))

        # os.rename を 2 回目以降失敗させる（PDF 後の thumb で失敗）
        original_rename = os.rename
        call_count = {"n": 0}

        def _flaky_rename(src, dst):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise OSError("simulated failure")
            return original_rename(src, dst)

        monkeypatch.setattr("services.file_manager.os.rename", _flaky_rename)

        with pytest.raises(OSError):
            FileManager.rename_with_assets("", "src", "dst", True, dirs)

        # ロールバックで元に戻っている
        assert os.path.exists(os.path.join(dirs["pdf"], "src"))
        assert not os.path.exists(os.path.join(dirs["pdf"], "dst"))


class TestDeleteWithAssets:
    def test_deletes_pdf_thumb_and_images(self, tmp_path):
        dirs = _make_dirs(tmp_path)
        open(os.path.join(dirs["pdf"], "book.pdf"), "w").close()
        open(os.path.join(dirs["thumb"], "book.jpg"), "w").close()
        os.makedirs(os.path.join(dirs["img"], "book"))
        open(os.path.join(dirs["img"], "book", "1.webp"), "w").close()

        FileManager.delete_with_assets("book.pdf", "", dirs)

        assert not os.path.exists(os.path.join(dirs["pdf"], "book.pdf"))
        assert not os.path.exists(os.path.join(dirs["thumb"], "book.jpg"))
        assert not os.path.exists(os.path.join(dirs["img"], "book"))

    def test_deletes_image_only_mode(self, tmp_path):
        """PDF 不在でも images があれば削除成功（image-only モード）。"""
        dirs = _make_dirs(tmp_path)
        os.makedirs(os.path.join(dirs["img"], "book"))
        open(os.path.join(dirs["img"], "book", "1.webp"), "w").close()

        FileManager.delete_with_assets("book.pdf", "", dirs)

        assert not os.path.exists(os.path.join(dirs["img"], "book"))

    def test_raises_when_neither_pdf_nor_images_exist(self, tmp_path):
        dirs = _make_dirs(tmp_path)

        with pytest.raises(FileNotFoundError):
            FileManager.delete_with_assets("missing.pdf", "", dirs)

    def test_continues_when_thumb_delete_fails(self, tmp_path, monkeypatch):
        """サムネイル削除に失敗してもメイン処理（PDF 削除）は完了する。"""
        dirs = _make_dirs(tmp_path)
        open(os.path.join(dirs["pdf"], "book.pdf"), "w").close()
        open(os.path.join(dirs["thumb"], "book.jpg"), "w").close()

        original_remove = os.remove

        def _flaky_remove(path):
            if path.endswith("book.jpg"):
                raise OSError("simulated thumb failure")
            return original_remove(path)

        monkeypatch.setattr("services.file_manager.os.remove", _flaky_remove)

        # 例外を投げない
        FileManager.delete_with_assets("book.pdf", "", dirs)

        # PDF は削除済み
        assert not os.path.exists(os.path.join(dirs["pdf"], "book.pdf"))
        # サムネイルは残ったまま
        assert os.path.exists(os.path.join(dirs["thumb"], "book.jpg"))

    def test_with_subpath(self, tmp_path):
        dirs = _make_dirs(tmp_path)
        os.makedirs(os.path.join(dirs["pdf"], "sub"))
        open(os.path.join(dirs["pdf"], "sub", "book.pdf"), "w").close()
        os.makedirs(os.path.join(dirs["img"], "sub"))
        os.makedirs(os.path.join(dirs["img"], "sub", "book"))

        FileManager.delete_with_assets("book.pdf", "sub", dirs)

        assert not os.path.exists(os.path.join(dirs["pdf"], "sub", "book.pdf"))
        assert not os.path.exists(os.path.join(dirs["img"], "sub", "book"))
