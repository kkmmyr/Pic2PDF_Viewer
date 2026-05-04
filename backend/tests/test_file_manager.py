"""
services.file_manager のユニットテスト。

実行方法:
    cd backend
    pytest tests/test_file_manager.py -v
"""
import sys
import os
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
