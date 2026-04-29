"""
アプリケーション設定モジュール。

データディレクトリパスの定義・初期化と、
ソース別ディレクトリ解決ヘルパーを提供する。
"""
import os
from typing import TypedDict
from dotenv import load_dotenv

# プロジェクトルートの .env を読み込む（存在しない場合は無視）
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

# ---------------------------------------------------------------------------
# データディレクトリパス定義
# ---------------------------------------------------------------------------
# backend/ の親ディレクトリ（プロジェクトルート）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# backend/data/
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# Generated (default)
MAIN_DATA_DIR      = os.path.join(DATA_DIR, "main")
PDF_DIR            = os.path.join(MAIN_DATA_DIR, "pdfs")
PDF_COMPRESSED_DIR = os.path.join(MAIN_DATA_DIR, "pdfs_compressed")
THUMBNAIL_DIR      = os.path.join(MAIN_DATA_DIR, "thumbnails")
IMAGES_DIR         = os.path.join(MAIN_DATA_DIR, "images")
COMPLETE_DIR       = os.path.join(MAIN_DATA_DIR, "complete")

# Kindle
KINDLE_DIR           = os.path.join(DATA_DIR, "kindle")
KINDLE_PDF_DIR       = os.path.join(KINDLE_DIR, "pdfs")
KINDLE_THUMBNAIL_DIR = os.path.join(KINDLE_DIR, "thumbnails")
KINDLE_IMAGES_DIR    = os.path.join(KINDLE_DIR, "images")

# Kindle Novel
KINDLE_NOVEL_DIR           = os.path.join(DATA_DIR, "kindle_novel")
KINDLE_NOVEL_PDF_DIR       = os.path.join(KINDLE_NOVEL_DIR, "pdfs")
KINDLE_NOVEL_THUMBNAIL_DIR = os.path.join(KINDLE_NOVEL_DIR, "thumbnails")
KINDLE_NOVEL_IMAGES_DIR    = os.path.join(KINDLE_NOVEL_DIR, "images")

# OCR 起動スクリプト
BATCH_OCR_LAUNCHER = os.path.join(PROJECT_ROOT, "kindle-pdf", "start_batch_ocr.bat")

# フロントエンド配信ディレクトリ（リリースモード用）
FRONTEND_DIST_DIR = os.path.join(PROJECT_ROOT, "frontend", "dist")

# Gemma 4 ツールディレクトリ（web_extract モジュールの場所）
# .env の GEMMA_TOOL_DIR で上書き可能
GEMMA_TOOL_DIR: str = os.environ.get("GEMMA_TOOL_DIR", r"D:\61.tool\Gemma 4")

# ---------------------------------------------------------------------------
# サポートファイル形式
# ---------------------------------------------------------------------------
SUPPORTED_IMAGE_FORMATS = ('.webp', '.jpg', '.jpeg', '.png')
SUPPORTED_WEBP_FORMAT = ('.webp',)
SUPPORTED_ZIP_FORMAT = ('.zip',)

# ---------------------------------------------------------------------------
# サムネイル設定
# ---------------------------------------------------------------------------
THUMBNAIL_HEIGHT = 500

# ---------------------------------------------------------------------------
# ジョブ管理設定
# ---------------------------------------------------------------------------
JOB_MAX_JOBS = 20
OCR_LOG_MAXLEN = 2000

# ---------------------------------------------------------------------------
# CORS 設定（環境変数で上書き可能）
# ---------------------------------------------------------------------------
_default_origins = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://localhost:5175,http://localhost:5176"
CORS_ORIGINS: list[str] = os.environ.get("ALLOWED_ORIGINS", _default_origins).split(",")

# ---------------------------------------------------------------------------
# ディレクトリ初期化
# ---------------------------------------------------------------------------
_REQUIRED_DIRS: list[str] = [
    PDF_DIR,
    PDF_COMPRESSED_DIR,
    THUMBNAIL_DIR,
    IMAGES_DIR,
    COMPLETE_DIR,
    KINDLE_PDF_DIR,
    KINDLE_THUMBNAIL_DIR,
    KINDLE_IMAGES_DIR,
    KINDLE_NOVEL_PDF_DIR,
    KINDLE_NOVEL_THUMBNAIL_DIR,
    KINDLE_NOVEL_IMAGES_DIR,
]


def ensure_directories() -> None:
    """必要なデータディレクトリをすべて作成する。"""
    for directory in _REQUIRED_DIRS:
        os.makedirs(directory, exist_ok=True)


ensure_directories()

# ---------------------------------------------------------------------------
# ソース別ディレクトリ解決
# ---------------------------------------------------------------------------
class SourceDirs(TypedDict):
    pdf: str
    thumb: str
    img: str
    thumb_url_prefix: str


def get_dirs_by_source(source: str) -> SourceDirs:
    """
    source 文字列に応じて PDF/サムネイル/画像のディレクトリを返す。

    Args:
        source: 'generated' | 'kindle' | 'novel'

    Returns:
        SourceDirs TypedDict
    """
    if source == "kindle":
        return {
            "pdf": KINDLE_PDF_DIR,
            "thumb": KINDLE_THUMBNAIL_DIR,
            "img": KINDLE_IMAGES_DIR,
            "thumb_url_prefix": "/kindle/thumbnails",
        }
    if source == "novel":
        return {
            "pdf": KINDLE_NOVEL_PDF_DIR,
            "thumb": KINDLE_NOVEL_THUMBNAIL_DIR,
            "img": KINDLE_NOVEL_IMAGES_DIR,
            "thumb_url_prefix": "/kindle_novel/thumbnails",
        }
    # generated (default)
    return {
        "pdf": PDF_COMPRESSED_DIR,
        "thumb": THUMBNAIL_DIR,
        "img": IMAGES_DIR,
        "thumb_url_prefix": "/thumbnails",
    }
