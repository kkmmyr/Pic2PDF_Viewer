"""
共通テストフィクスチャ。

router テスト・統合テストで使う `tmp_data_dir` / `client` / `make_pdf` 等を集約する。
詳細は docs/06_リファクタリング/テスト整備計画書.md §4.1 を参照。
"""
import os
import sys

import fitz
import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ---------------------------------------------------------------------------
# データディレクトリの差し替え
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """`config` の各データディレクトリを tmp_path 配下に差し替える。

    返り値はソース別の dict（pdf / thumb / img / complete を保持）。
    routers / services 側はモジュール変数として `from config import X` で
    取り込んでいるため、両方を monkeypatch する必要がある。
    """
    main = tmp_path / "doujin"
    kindle = tmp_path / "comic"
    novel = tmp_path / "kindle_novel"
    meta_dir = tmp_path / "meta"

    lance_path = str(tmp_path / "novel.lancedb")
    paths = {
        "DATA_DIR": str(tmp_path),
        "MAIN_DATA_DIR": str(main),
        "PDF_COMPRESSED_DIR": str(main / "pdfs_compressed"),
        "THUMBNAIL_DIR": str(main / "thumbnails"),
        "IMAGES_DIR": str(main / "images"),
        "COMPLETE_DIR": str(main / "complete"),
        "KINDLE_DIR": str(kindle),
        "KINDLE_PDF_DIR": str(kindle / "pdfs"),
        "KINDLE_THUMBNAIL_DIR": str(kindle / "thumbnails"),
        "KINDLE_IMAGES_DIR": str(kindle / "images"),
        "KINDLE_NOVEL_DIR": str(novel),
        "KINDLE_NOVEL_PDF_DIR": str(novel / "pdfs"),
        "KINDLE_NOVEL_THUMBNAIL_DIR": str(novel / "thumbnails"),
        "KINDLE_NOVEL_IMAGES_DIR": str(novel / "images"),
        "NOVEL_DB_DIR": str(tmp_path / "novel_db"),
        "NOVEL_DB_PATH": str(tmp_path / "novel_db" / "novel.db"),
        "NOVEL_DB_LANCE_PATH": lance_path,
    }

    # 必要ディレクトリを作成
    for key, p in paths.items():
        if key.endswith("_DIR"):
            os.makedirs(p, exist_ok=True)
    os.makedirs(meta_dir, exist_ok=True)

    # config 本体を差し替え
    import config
    for key, p in paths.items():
        monkeypatch.setattr(config, key, p, raising=True)

    # モジュール側で `from config import X` で取り込んでいる場合の差し替え
    _patch_imported_paths(monkeypatch, paths)

    # LanceDB グローバル接続をリセット（テスト用 tmp_path に再接続させる）
    try:
        import services.novel_db.lance_store as _lance
        monkeypatch.setattr(_lance, "NOVEL_DB_LANCE_PATH", lance_path)
        _lance.reset_db()
    except ImportError:
        pass

    return {
        "root": str(tmp_path),
        "main": str(main),
        "comic": str(kindle),
        "novel": str(novel),
        "meta": str(meta_dir),
        **paths,
    }


def _patch_imported_paths(monkeypatch, paths: dict) -> None:
    """`from config import X` で取り込まれたモジュール変数を差し替える。"""
    targets = [
        ("services.meta_db", "DATA_DIR", paths["DATA_DIR"]),
        ("routers.generate", "PDF_COMPRESSED_DIR", paths["PDF_COMPRESSED_DIR"]),
        ("routers.generate", "THUMBNAIL_DIR", paths["THUMBNAIL_DIR"]),
        ("routers.generate", "IMAGES_DIR", paths["IMAGES_DIR"]),
        ("routers.generate", "COMPLETE_DIR", paths["COMPLETE_DIR"]),
        # novel_db: 各モジュールが `from config import` でキャプチャしている定数
        ("services.novel_db.connection", "NOVEL_DB_DIR", paths["NOVEL_DB_DIR"]),
        ("services.novel_db.connection", "NOVEL_DB_PATH", paths["NOVEL_DB_PATH"]),
        ("services.novel_db.builder", "KINDLE_NOVEL_PDF_DIR", paths["KINDLE_NOVEL_PDF_DIR"]),
        ("services.novel_db.builder", "KINDLE_NOVEL_IMAGES_DIR", paths["KINDLE_NOVEL_IMAGES_DIR"]),
        ("services.novel_db.library", "KINDLE_NOVEL_IMAGES_DIR", paths["KINDLE_NOVEL_IMAGES_DIR"]),
        ("services.novel_db.job_queue", "KINDLE_NOVEL_PDF_DIR", paths["KINDLE_NOVEL_PDF_DIR"]),
    ]
    for module, attr, value in targets:
        try:
            __import__(module)
            mod = sys.modules[module]
            if hasattr(mod, attr):
                monkeypatch.setattr(mod, attr, value, raising=True)
        except ImportError:
            pass


# ---------------------------------------------------------------------------
# TestClient
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_data_dir):
    """`TestClient(app)` を返す。tmp_data_dir 適用済み。"""
    from fastapi.testclient import TestClient

    from main import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# PDF / WebP 生成ヘルパー
# ---------------------------------------------------------------------------

@pytest.fixture
def make_pdf():
    """指定パスに page_count ページの PDF を生成する関数。"""
    def _make(path: str, page_count: int = 1, width: int = 400, height: int = 600) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        doc = fitz.open()
        for i in range(page_count):
            page = doc.new_page(width=width, height=height)
            page.insert_text((50, 50), f"Page {i + 1}")
        doc.save(path)
        doc.close()

    return _make


@pytest.fixture
def make_webp():
    """指定パスに WebP 画像を生成する関数。"""
    def _make(path: str, color: tuple = (255, 0, 0), size: tuple = (100, 100)) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        img = Image.new("RGB", size, color)
        img.save(path, "WEBP")

    return _make
