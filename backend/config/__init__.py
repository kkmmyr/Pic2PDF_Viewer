"""
アプリケーション設定モジュール。

データディレクトリパスの定義・初期化と、
ソース別ディレクトリ解決ヘルパーを提供する。

Novel DB の env 設定（モデル・LLM・検索パラメータ等）は config.novel_db に分離。
"""
import os
from typing import TypedDict

from dotenv import load_dotenv

# プロジェクトルートの .env を読み込む（存在しない場合は無視）
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))

# ---------------------------------------------------------------------------
# データディレクトリパス定義
# ---------------------------------------------------------------------------
# backend/ の親ディレクトリ（プロジェクトルート）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# デフォルトのローカル data/ パス（backend/data/）
_DEFAULT_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# メインデータディレクトリ（画像・PDF・サムネイル・hitomi JSON）
# env: PIC2PDF_DATA_DIR で OneDrive 等の共有場所に変更可能
DATA_DIR = os.environ.get("PIC2PDF_DATA_DIR", _DEFAULT_DATA_DIR)

# Doujin (default)
MAIN_DATA_DIR      = os.path.join(DATA_DIR, "doujin")
PDF_COMPRESSED_DIR = os.path.join(MAIN_DATA_DIR, "pdfs_compressed")
THUMBNAIL_DIR      = os.path.join(MAIN_DATA_DIR, "thumbnails")
IMAGES_DIR         = os.path.join(MAIN_DATA_DIR, "images")
COMPLETE_DIR       = os.path.join(MAIN_DATA_DIR, "complete")
# Linux サーバー側でファイルを受け取る入力ディレクトリ（Samba 共有する）
# env: DOUJIN_INPUT_DIR で上書き可能
DOUJIN_INPUT_DIR   = os.environ.get("DOUJIN_INPUT_DIR", os.path.join(MAIN_DATA_DIR, "input"))

# Comic
KINDLE_DIR           = os.path.join(DATA_DIR, "comic")
KINDLE_PDF_DIR       = os.path.join(KINDLE_DIR, "pdfs")
KINDLE_THUMBNAIL_DIR = os.path.join(KINDLE_DIR, "thumbnails")
KINDLE_IMAGES_DIR    = os.path.join(KINDLE_DIR, "images")

# Kindle Novel
KINDLE_NOVEL_DIR           = os.path.join(DATA_DIR, "kindle_novel")
KINDLE_NOVEL_PDF_DIR       = os.path.join(KINDLE_NOVEL_DIR, "pdfs")
KINDLE_NOVEL_THUMBNAIL_DIR = os.path.join(KINDLE_NOVEL_DIR, "thumbnails")
# 画像出力先は env で上書き可能（キャプチャツール kindle-pdf/ と同じ env を共有）
KINDLE_NOVEL_IMAGES_DIR    = os.environ.get(
    "KINDLE_NOVEL_IMAGES_DIR",
    os.path.join(KINDLE_NOVEL_DIR, "images"),
)

# hitomi.la 新着監視データ（JSON ファイル群。DATA_DIR 配下で共有可）
HITOMI_DATA_DIR = os.path.join(DATA_DIR, "hitomi")

# 書誌メタ DB（SQLite。OneDrive 非推奨のためローカルに固定）
# env: META_DB_DIR で個別パスを上書き可能
META_DB_DIR = os.environ.get("META_DB_DIR", _DEFAULT_DATA_DIR)

# Novel DB（SQLite + LanceDB。OneDrive 非推奨のためローカルに固定）
# env: NOVEL_DB_DIR で個別パスを上書き可能
NOVEL_DB_DIR  = os.environ.get("NOVEL_DB_DIR", os.path.join(_DEFAULT_DATA_DIR, "novel_db"))
NOVEL_DB_PATH = os.path.join(NOVEL_DB_DIR, "novel.db")

# Novel DB の env 設定（モデル・LLM・検索パラメータ等）は novel_db サブモジュールに分離。
# `from config import NOVEL_DB_*` は従来通り動作する。
from .novel_db import *  # noqa: E402 F401 F403

# フロントエンド配信ディレクトリ（リリースモード用）
FRONTEND_DIST_DIR = os.path.join(PROJECT_ROOT, "frontend", "dist")

# Amazon 購入履歴 CSV ルートディレクトリ（環境変数で設定。未設定時は CSV インポート無効）
AMAZON_DATA_DIR: str | None = os.environ.get("AMAZON_DATA_DIR") or None

# Gemma 4 ツールディレクトリ（web_extract モジュールの場所。未設定時は Gemma 連携無効）
GEMMA_TOOL_DIR: str | None = os.environ.get("GEMMA_TOOL_DIR") or None

# meta.db バックアップ先（env: META_DB_BACKUP_DIR。未設定時はバックアップ無効）
META_DB_BACKUP_DIR: str | None = os.environ.get("META_DB_BACKUP_DIR") or None

# ---------------------------------------------------------------------------
# ソース識別子
# ---------------------------------------------------------------------------
VALID_SOURCES: tuple[str, ...] = ("doujin", "comic", "novel")

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
# ZIP 解凍上限（zip bomb 対策）
# 個人ツールの想定範囲（1 冊 ≒ 〜1000 ページ × 〜500KB WebP ≒ 500MB）に
# 余裕を持たせた値。これを超える ZIP は generate ジョブで弾く。
# ---------------------------------------------------------------------------
ZIP_MAX_ENTRIES: int = 5000
ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES: int = 2 * 1024**3   # 2 GB
ZIP_MAX_PER_FILE_BYTES: int = 50 * 1024**2            # 50 MB / 1 枚

# ---------------------------------------------------------------------------
# CORS 設定（環境変数で上書き可能）
# ---------------------------------------------------------------------------
_default_origins = "http://localhost:5176,http://127.0.0.1:5176"
CORS_ORIGINS: list[str] = os.environ.get("ALLOWED_ORIGINS", _default_origins).split(",")

# ---------------------------------------------------------------------------
# ディレクトリ初期化
# ---------------------------------------------------------------------------
_REQUIRED_DIRS: list[str] = [
    THUMBNAIL_DIR,
    IMAGES_DIR,
    COMPLETE_DIR,
    KINDLE_PDF_DIR,
    KINDLE_THUMBNAIL_DIR,
    KINDLE_IMAGES_DIR,
    KINDLE_NOVEL_PDF_DIR,
    KINDLE_NOVEL_THUMBNAIL_DIR,
    KINDLE_NOVEL_IMAGES_DIR,
    HITOMI_DATA_DIR,
    NOVEL_DB_DIR,
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
        source: 'doujin' | 'comic' | 'novel'

    Returns:
        SourceDirs TypedDict
    """
    if source == "comic":
        return {
            "pdf": KINDLE_PDF_DIR,
            "thumb": KINDLE_THUMBNAIL_DIR,
            "img": KINDLE_IMAGES_DIR,
            "thumb_url_prefix": "/comic/thumbnails",
        }
    if source == "novel":
        return {
            "pdf": KINDLE_NOVEL_PDF_DIR,
            "thumb": KINDLE_NOVEL_THUMBNAIL_DIR,
            "img": KINDLE_NOVEL_IMAGES_DIR,
            "thumb_url_prefix": "/kindle_novel/thumbnails",
        }
    # doujin (default)
    return {
        "pdf": PDF_COMPRESSED_DIR,
        "thumb": THUMBNAIL_DIR,
        "img": IMAGES_DIR,
        "thumb_url_prefix": "/thumbnails",
    }
