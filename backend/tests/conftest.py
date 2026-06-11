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
    全モジュールが `import config; config.X` で参照するため config 本体のみ差し替えれば十分。
    """
    main = tmp_path / "doujin"
    kindle = tmp_path / "comic"
    novel = tmp_path / "kindle_novel"
    meta_dir = tmp_path / "meta"

    lance_path = str(tmp_path / "novel.lancedb")
    paths = {
        "DATA_DIR": str(tmp_path),
        "META_DB_DIR": str(tmp_path),
        "MAIN_DATA_DIR": str(main),
        "PDF_COMPRESSED_DIR": str(main / "pdfs_compressed"),
        "THUMBNAIL_DIR": str(main / "thumbnails"),
        "IMAGES_DIR": str(main / "images"),
        "COMPLETE_DIR": str(main / "complete"),
        "DOUJIN_INPUT_DIR": str(main / "input"),
        "COMIC_DIR": str(kindle),
        "COMIC_PDF_DIR": str(kindle / "pdfs"),
        "COMIC_THUMBNAIL_DIR": str(kindle / "thumbnails"),
        "COMIC_IMAGES_DIR": str(kindle / "images"),
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

    # config 本体を差し替え（全モジュールが config.X で参照するためこれだけで十分）
    import config
    for key, p in paths.items():
        monkeypatch.setattr(config, key, p, raising=True)

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


@pytest.fixture
def make_png():
    """指定パスに PNG 画像を生成する関数（Kindle キャプチャのテスト用）。"""
    def _make(path: str, color: tuple = (0, 128, 255), size: tuple = (100, 100)) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        img = Image.new("RGB", size, color)
        img.save(path, "PNG")

    return _make
