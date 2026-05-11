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

# Novel DB（小説テキスト検索・RAG 機能の SQLite ファイル格納）
NOVEL_DB_DIR  = os.path.join(DATA_DIR, "novel_db")
NOVEL_DB_PATH = os.path.join(NOVEL_DB_DIR, "novel.db")

# Novel DB の埋め込みモデル / LLM（Ollama）
NOVEL_DB_OLLAMA_BASE_URL = os.environ.get("NOVEL_DB_OLLAMA_BASE_URL", "http://localhost:11434")
NOVEL_DB_EMBED_MODEL     = os.environ.get("NOVEL_DB_EMBED_MODEL", "bge-m3")
NOVEL_DB_EMBED_DIM       = 1024  # bge-m3 の出力次元
NOVEL_DB_LLM_MODEL       = os.environ.get("NOVEL_DB_LLM_MODEL", "qwen3.6-iq4xs")
# 主要登場人物抽出用の軽量モデル（短答型タスク。thinking で num_predict を
# 消費する 26b と異なり、e4b は応答が速く character 抽出に向く）
NOVEL_DB_CHAR_EXTRACT_MODEL = os.environ.get("NOVEL_DB_CHAR_EXTRACT_MODEL", "gemma4:e4b")

# B-9 Contextual Retrieval のチャンクコンテキスト生成モデル。
# Anthropic の Contextual Retrieval blog では「位置説明は単純なタスクなので
# 軽量モデルで十分」と推奨されており、gemma4:e4b で代用する。
# 品質不足が確認されたら NOVEL_DB_LLM_MODEL（qwen3.6:35b-a3b）にフォールバック。
NOVEL_DB_CONTEXT_MODEL = os.environ.get("NOVEL_DB_CONTEXT_MODEL", "gemma4:e4b")

# Novel DB 検索のデフォルト値
# - MIN_BODY_CHARS: 章扉・目次・人物紹介・あとがき等の薄いページを検索対象から除外する閾値
# - QA_TOP_K: RAG 質問応答で Gemma に渡すページ数（多いほど深い回答だが応答時間も伸びる）
# - QA_MAX_PER_BOOK: scope=all / series での書籍ごと取得上限（ざっくり質問が特定冊に偏らないよう均等化）
# - BODY_PAGE_MARGIN: 各書籍の先頭 / 末尾の除外ページ数（表紙・目次・あとがき・解説・奥付）
NOVEL_DB_MIN_BODY_CHARS    = 300
# B-13 段階 A（2026-05-11 採用）: top_k を 16 → 32 に拡大。
# Qwen IQ4_XS（B-12）採用後の num_ctx 拡大に合わせ、ヒットページを多く取って RAG 品質を上げる。
# 環境変数 NOVEL_DB_QA_TOP_K で上書き可（A/B/C 段階の切替やベンチ用途）
NOVEL_DB_QA_TOP_K          = int(os.environ.get("NOVEL_DB_QA_TOP_K", "32"))
NOVEL_DB_QA_MAX_PER_BOOK   = 2
NOVEL_DB_BODY_PAGE_MARGIN  = 5
# B-8: scope=all / scope=series で QA プロンプトに含める書籍サマリの上限件数。
# 現状 11 冊なので 11 でほぼ全冊カバー。書籍数が増えたら適宜下げる
NOVEL_DB_QA_TOP_SUMMARIES  = 11
# B-13 段階 A: QA 時の num_ctx。従来 8192 だったが、top_k=32 × 平均 600 字 = 約 12k 字 +
# 全 11 冊サマリ ~11k 字 + テンプレート + 質問で約 24k 字 ≒ ~15k tokens となり 8192 を超えるため、
# 16384 に拡大して切り詰めを防ぐ。応答時間は約 +20〜30% の見込み（量比例）
# 環境変数 NOVEL_DB_QA_NUM_CTX で上書き可（段階 B=32768 / C=131072 への切替に使う）
NOVEL_DB_QA_NUM_CTX        = int(os.environ.get("NOVEL_DB_QA_NUM_CTX", "16384"))

# OCR 起動スクリプト
BATCH_OCR_LAUNCHER = os.path.join(PROJECT_ROOT, "kindle-pdf", "start_batch_ocr.bat")

# フロントエンド配信ディレクトリ（リリースモード用）
FRONTEND_DIST_DIR = os.path.join(PROJECT_ROOT, "frontend", "dist")

# Gemma 4 ツールディレクトリ（web_extract モジュールの場所）
# .env の GEMMA_TOOL_DIR で上書き可能
GEMMA_TOOL_DIR: str = os.environ.get("GEMMA_TOOL_DIR", r"D:\61.tool\Gemma 4")

# ---------------------------------------------------------------------------
# ソース識別子
# ---------------------------------------------------------------------------
VALID_SOURCES: tuple[str, ...] = ("generated", "kindle", "novel")

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
