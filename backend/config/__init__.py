"""
アプリケーション設定モジュール。

データディレクトリパスの定義・初期化と、
ソース別ディレクトリ解決ヘルパーを提供する。

Novel DB の env 設定（モデル・LLM・検索パラメータ等）は config.novel_db に分離。
"""

from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# プロジェクトルートの .env を読み込む（存在しない場合は無視）
load_dotenv(Path(__file__).parent.parent.parent / ".env")

_BACKEND_DIR = Path(__file__).parent.parent
_DEFAULT_DATA_DIR = _BACKEND_DIR / "data"


class _AppSettings(BaseSettings):
    """アプリケーション設定。起動時に環境変数から読み込む。

    .env は上の load_dotenv() で os.environ に読み込み済みのため、
    env_file は指定せず os.environ のみを参照する。
    """

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    # メインデータディレクトリ（画像・PDF・サムネイル・hitomi JSON）
    PIC2PDF_DATA_DIR: Path = _DEFAULT_DATA_DIR
    # Doujin 入力ディレクトリ（None → PIC2PDF_DATA_DIR/doujin/input）
    DOUJIN_INPUT_DIR: Path | None = None
    # Kindle Novel 画像ディレクトリ（None → PIC2PDF_DATA_DIR/kindle_novel/images）
    KINDLE_NOVEL_IMAGES_DIR: Path | None = None
    # 書誌メタ DB ディレクトリ（OneDrive 非推奨のためローカル固定が基本）
    META_DB_DIR: Path = _DEFAULT_DATA_DIR
    # Novel DB ディレクトリ
    NOVEL_DB_DIR: Path = _DEFAULT_DATA_DIR / "novel_db"
    # CORS 許可オリジン（カンマ区切り文字列）
    ALLOWED_ORIGINS: str = "http://localhost:5176,http://127.0.0.1:5176"
    # Amazon 購入履歴 CSV ルートディレクトリ（未設定時は無効）
    AMAZON_DATA_DIR: Path | None = None
    # Gemma 4 ツールディレクトリ（未設定時は Gemma 連携無効）
    GEMMA_TOOL_DIR: Path | None = None
    # meta2.db バックアップ先（未設定時はバックアップ無効）
    META_DB_BACKUP_DIR: Path | None = None
    # LinuxサーバーのDB世代バックアップ先・保持日数・復元試験先
    SERVER_BACKUP_DIR: Path | None = None
    SERVER_BACKUP_RETENTION_DAYS: int = 14
    SERVER_RESTORE_TEST_DIR: Path | None = None
    # OCR venv の Python 実行ファイルパス（未設定時はプラットフォーム既定値）
    # Windows: D:\61.tool\common\ocr\venv\Scripts\python.exe
    # Mac/Linux: ~/.venv/ocr/bin/python
    OCR_PYTHON: str | None = None
    # OCR パッケージディレクトリ（ocr_engine.py が置かれた common/ocr/ パス）
    # ocr_worker.py サブプロセスに OCR_PATH 環境変数として渡される
    OCR_PACKAGE_PATH: str | None = None
    # OCRエンジン（surya2 / yomitoku）
    OCR_ENGINE: str = "surya2"
    # Surya OCR 2 OpenAI互換推論サーバー
    SURYA_INFERENCE_URL: str = "http://127.0.0.1:8768/v1"
    SURYA_MODEL: str = "surya-ocr-2"
    # model/mmproj/llama.cpp の固定資材を識別する監査用文字列
    SURYA_MODEL_REVISION: str = "unversioned"
    SURYA_LLAMA_SERVER_PATH: Path | None = None
    SURYA_MODEL_PATH: Path | None = None
    SURYA_MMPROJ_PATH: Path | None = None
    SURYA_REQUEST_TIMEOUT_SEC: float = 600.0
    SURYA_MAX_ATTEMPTS: int = 3
    OCR_QUALITY_MIN_INK_COVERAGE: float = 0.85
    # 同人誌入力フォルダの自動監視を有効にするか
    DOUJIN_WATCH_ENABLED: bool = True
    # 監視間隔（秒）
    DOUJIN_WATCH_INTERVAL_SEC: int = 15
    # hitomi 新着監視の実行結果を通知する Discord Webhook URL（未設定時は通知無効）
    HITOMI_DISCORD_WEBHOOK_URL: str | None = None


_s = _AppSettings()
app_settings = _s  # public singleton

# ---------------------------------------------------------------------------
# データディレクトリパス定義
# ---------------------------------------------------------------------------
PROJECT_ROOT = str(_BACKEND_DIR.parent)

DATA_DIR = str(_s.PIC2PDF_DATA_DIR)
_SERVER_STORAGE_ROOT = _s.PIC2PDF_DATA_DIR.parent
SERVER_BACKUP_DIR = str(_s.SERVER_BACKUP_DIR or _SERVER_STORAGE_ROOT / "backups")
SERVER_BACKUP_RETENTION_DAYS: int = _s.SERVER_BACKUP_RETENTION_DAYS
SERVER_RESTORE_TEST_DIR = str(_s.SERVER_RESTORE_TEST_DIR or _SERVER_STORAGE_ROOT / "restore-tests")

# Doujin
MAIN_DATA_DIR = str(_s.PIC2PDF_DATA_DIR / "doujin")
THUMBNAIL_DIR = str(_s.PIC2PDF_DATA_DIR / "doujin" / "thumbnails")
IMAGES_DIR = str(_s.PIC2PDF_DATA_DIR / "doujin" / "images")
COMPLETE_DIR = str(_s.PIC2PDF_DATA_DIR / "doujin" / "complete")
DOUJIN_INPUT_DIR = str(_s.DOUJIN_INPUT_DIR or _s.PIC2PDF_DATA_DIR / "doujin" / "input")

# Comic
COMIC_DIR = str(_s.PIC2PDF_DATA_DIR / "comic")
COMIC_PDF_DIR = str(_s.PIC2PDF_DATA_DIR / "comic" / "pdfs")
COMIC_THUMBNAIL_DIR = str(_s.PIC2PDF_DATA_DIR / "comic" / "thumbnails")
COMIC_IMAGES_DIR = str(_s.PIC2PDF_DATA_DIR / "comic" / "images")

# Kindle Novel
KINDLE_NOVEL_DIR = str(_s.PIC2PDF_DATA_DIR / "kindle_novel")
KINDLE_NOVEL_PDF_DIR = str(_s.PIC2PDF_DATA_DIR / "kindle_novel" / "pdfs")
KINDLE_NOVEL_THUMBNAIL_DIR = str(_s.PIC2PDF_DATA_DIR / "kindle_novel" / "thumbnails")
KINDLE_NOVEL_IMAGES_DIR = str(_s.KINDLE_NOVEL_IMAGES_DIR or _s.PIC2PDF_DATA_DIR / "kindle_novel" / "images")

# hitomi.la 新着監視データ
HITOMI_DATA_DIR = str(_s.PIC2PDF_DATA_DIR / "hitomi")

# 書誌メタ DB（SQLite）
META_DB_DIR = str(_s.META_DB_DIR)

# Novel DB（SQLite + LanceDB）
NOVEL_DB_DIR = str(_s.NOVEL_DB_DIR)
NOVEL_DB_PATH = str(_s.NOVEL_DB_DIR / "novel.db")

# Novel DB の env 設定（モデル・LLM・検索パラメータ等）は novel_db サブモジュールに分離。
# `from config import NOVEL_DB_*` は従来通り動作する。
from .novel_db import *  # noqa: E402, F403

# フロントエンド配信ディレクトリ（リリースモード用）
FRONTEND_DIST_DIR = str(_BACKEND_DIR.parent / "frontend" / "dist")

# オプション設定（未設定時は None）
AMAZON_DATA_DIR: str | None = str(_s.AMAZON_DATA_DIR) if _s.AMAZON_DATA_DIR else None
GEMMA_TOOL_DIR: str | None = str(_s.GEMMA_TOOL_DIR) if _s.GEMMA_TOOL_DIR else None
META_DB_BACKUP_DIR: str | None = str(_s.META_DB_BACKUP_DIR) if _s.META_DB_BACKUP_DIR else None
HITOMI_DISCORD_WEBHOOK_URL: str | None = _s.HITOMI_DISCORD_WEBHOOK_URL or None

# ---------------------------------------------------------------------------
# ソース識別子
# ---------------------------------------------------------------------------
VALID_SOURCES: tuple[str, ...] = ("doujin", "comic", "novel")

# ---------------------------------------------------------------------------
# サポートファイル形式
# ---------------------------------------------------------------------------
SUPPORTED_IMAGE_FORMATS = (".webp", ".jpg", ".jpeg", ".png")
SUPPORTED_WEBP_FORMAT = (".webp",)
SUPPORTED_ZIP_FORMAT = (".zip",)

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
# 同人誌フォルダ監視設定
# ---------------------------------------------------------------------------
DOUJIN_WATCH_ENABLED: bool = _s.DOUJIN_WATCH_ENABLED
DOUJIN_WATCH_INTERVAL_SEC: int = _s.DOUJIN_WATCH_INTERVAL_SEC

# ---------------------------------------------------------------------------
# ZIP 解凍上限（zip bomb 対策）
# 個人ツールの想定範囲（1 冊 ≒ 〜1000 ページ × 〜500KB WebP ≒ 500MB）に
# 余裕を持たせた値。これを超える ZIP は generate ジョブで弾く。
# ---------------------------------------------------------------------------
ZIP_MAX_ENTRIES: int = 5000
ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES: int = 2 * 1024**3  # 2 GB
ZIP_MAX_PER_FILE_BYTES: int = 50 * 1024**2  # 50 MB / 1 枚

# ---------------------------------------------------------------------------
# CORS 設定
# ---------------------------------------------------------------------------
CORS_ORIGINS: list[str] = _s.ALLOWED_ORIGINS.split(",")

# ---------------------------------------------------------------------------
# ディレクトリ初期化
# ---------------------------------------------------------------------------
_REQUIRED_DIRS: list[str] = [
    THUMBNAIL_DIR,
    IMAGES_DIR,
    COMPLETE_DIR,
    COMIC_PDF_DIR,
    COMIC_THUMBNAIL_DIR,
    COMIC_IMAGES_DIR,
    KINDLE_NOVEL_PDF_DIR,
    KINDLE_NOVEL_THUMBNAIL_DIR,
    KINDLE_NOVEL_IMAGES_DIR,
    HITOMI_DATA_DIR,
    NOVEL_DB_DIR,
]


def ensure_directories() -> None:
    """必要なデータディレクトリをすべて作成する。"""
    for directory in _REQUIRED_DIRS:
        Path(directory).mkdir(parents=True, exist_ok=True)


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
    data_dir = app_settings.PIC2PDF_DATA_DIR
    novel_images = str(app_settings.KINDLE_NOVEL_IMAGES_DIR or data_dir / "kindle_novel" / "images")
    if source == "comic":
        return {
            "pdf": str(data_dir / "comic" / "pdfs"),
            "thumb": str(data_dir / "comic" / "thumbnails"),
            "img": str(data_dir / "comic" / "images"),
            "thumb_url_prefix": "/comic/thumbnails",
        }
    if source == "novel":
        return {
            "pdf": str(data_dir / "kindle_novel" / "pdfs"),
            "thumb": str(data_dir / "kindle_novel" / "thumbnails"),
            "img": novel_images,
            "thumb_url_prefix": "/kindle_novel/thumbnails",
        }
    # doujin (default)
    return {
        "pdf": str(data_dir / "doujin" / "pdfs_compressed"),
        "thumb": str(data_dir / "doujin" / "thumbnails"),
        "img": str(data_dir / "doujin" / "images"),
        "thumb_url_prefix": "/thumbnails",
    }
