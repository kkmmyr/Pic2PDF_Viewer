"""
Novel DB（小説 RAG 機能）の設定値。

`config/__init__.py` から `from .novel_db import *` でインポートされる。
直接インポートも可能: `from config.novel_db import NOVEL_DB_LLM_MODEL`
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_LANCE_PATH = str(Path(__file__).parent.parent / "data" / "novel.lancedb")


class _NovelDbSettings(BaseSettings):
    """Novel DB の env 設定。起動時に型検証・変換を行う。

    .env は config/__init__.py の load_dotenv() で os.environ に読み込み済みのため、
    ここでは env_file を指定せず os.environ のみを参照する。
    """

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    # ---------------------------------------------------------------------------
    # LanceDB ベクトルストアパス
    # ---------------------------------------------------------------------------
    NOVEL_DB_LANCE_PATH: str = _DEFAULT_LANCE_PATH

    # ---------------------------------------------------------------------------
    # 埋め込みモデル / LLM
    # ---------------------------------------------------------------------------
    NOVEL_DB_OLLAMA_BASE_URL: str = "http://localhost:11434"
    NOVEL_DB_EMBED_MODEL: str = "bge-m3"
    # 既定 0 = CPU 推論。llama-server（Qwen 35B）に VRAM を譲るため。
    # GPU に戻すなら NOVEL_DB_EMBED_NUM_GPU=99 を設定して uvicorn を再起動。
    NOVEL_DB_EMBED_NUM_GPU: int = 0
    NOVEL_DB_LLM_MODEL: str = "qwen3.6-iq4xs"
    # 既定 `llama_server`（実機ベンチで tg 5× 高速化、scope=all 応答 24s→14s）。
    # Phase C で `ollama` 分岐撤去。未知の値は LLMError。
    NOVEL_DB_LLM_BACKEND: str = "llama_server"
    NOVEL_DB_LLAMA_SERVER_URL: str = "http://127.0.0.1:11435"
    # 主要登場人物抽出用モデル（短答型タスク）。
    # 2026-06-07 比較検証: gemma4:12b は e4b より平均 40% 速く（8.8s vs 14.9s/page）、
    # 一人称視点ページで e4b が返す ['私','猿ども'] 等のノイズを 12b が正しく [] にした。
    NOVEL_DB_CHAR_EXTRACT_MODEL: str = "gemma4:12b"
    # B-9 Contextual Retrieval のチャンクコンテキスト生成モデル。
    # 2026-06-07 比較検証: gemma4:12b は e4b より平均 13% 速く（10.3s vs 11.8s/chunk）、
    # 場面の具体性（固有名詞・状況説明）が高い傾向のため 12b に変更。
    # 品質不足が確認されたら NOVEL_DB_LLM_MODEL（qwen3.6:35b-a3b）にフォールバック。
    #
    # TODO(Step5高速化): Gemma4 MTP (Multi-Token Prediction) — llama.cpp 公式対応待ち
    NOVEL_DB_CONTEXT_MODEL: str = "gemma4:12b"
    # §4.5 本構築統合: キャラ抽出 / チャンク文脈生成のバックエンド切替
    # "ollama" (既定): Ollama 経由で gemma4:e4b を使用
    # "qwen"         : llama-server の Qwen に統一（thinking は _DEFAULT_THINK=False で自動抑制）
    NOVEL_DB_GEMMA_BACKEND: str = "ollama"

    # ---------------------------------------------------------------------------
    # 検索パラメータ
    # - QA_TOP_K: RAG 質問応答で Gemma に渡すページ数
    # - QA_NUM_CTX: QA 時の num_ctx（B-13 段階 B: 32768）
    # ---------------------------------------------------------------------------
    # B-13 段階 A→B（2026-05-11 採用）: top_k を 16 → 32 (A) → 64 (B) に段階拡大。
    NOVEL_DB_QA_TOP_K: int = 64
    # B-13 段階 B（2026-05-11 採用）: 32768（llama-server を -c 36864 で起動する必要あり）。
    NOVEL_DB_QA_NUM_CTX: int = 32768

    # B-11 Query Expansion（2026-05-11 採用）
    NOVEL_DB_QA_EXPAND_ENABLED: bool = True
    NOVEL_DB_QA_EXPAND_N: int = 3
    # 2026-06-07: gemma4:12b は e4b より平均 22% 速く品質は同等。
    NOVEL_DB_QA_EXPAND_MODEL: str = "gemma4:12b"

    # B-13 段階 C（scope=book で本文を丸ごと読み込むモード）
    NOVEL_DB_QA_FULL_BOOK_MODE: bool = True
    NOVEL_DB_QA_FULL_BOOK_NUM_CTX: int = 131072


_s = _NovelDbSettings()
novel_db_settings = _s  # public singleton

# ---------------------------------------------------------------------------
# モジュールレベル定数として再公開（`from config import NOVEL_DB_*` 互換）
# ---------------------------------------------------------------------------
NOVEL_DB_LANCE_PATH = _s.NOVEL_DB_LANCE_PATH
NOVEL_DB_OLLAMA_BASE_URL = _s.NOVEL_DB_OLLAMA_BASE_URL
NOVEL_DB_EMBED_MODEL = _s.NOVEL_DB_EMBED_MODEL
NOVEL_DB_EMBED_DIM = 1024  # bge-m3 の出力次元（固定値）
NOVEL_DB_EMBED_NUM_GPU = _s.NOVEL_DB_EMBED_NUM_GPU
NOVEL_DB_LLM_MODEL = _s.NOVEL_DB_LLM_MODEL
NOVEL_DB_LLM_BACKEND = _s.NOVEL_DB_LLM_BACKEND
NOVEL_DB_LLAMA_SERVER_URL = _s.NOVEL_DB_LLAMA_SERVER_URL
NOVEL_DB_CHAR_EXTRACT_MODEL = _s.NOVEL_DB_CHAR_EXTRACT_MODEL
NOVEL_DB_CONTEXT_MODEL = _s.NOVEL_DB_CONTEXT_MODEL
NOVEL_DB_GEMMA_BACKEND = _s.NOVEL_DB_GEMMA_BACKEND
NOVEL_DB_MIN_BODY_CHARS = 300  # 固定値（薄いページ除外閾値）
NOVEL_DB_QA_TOP_K = _s.NOVEL_DB_QA_TOP_K
NOVEL_DB_QA_MAX_PER_BOOK = 5  # 固定値（書籍ごと取得上限）
NOVEL_DB_BODY_PAGE_MARGIN = 5  # 固定値（先頭/末尾の除外ページ数）
NOVEL_DB_QA_TOP_SUMMARIES = 11  # 固定値（サマリ上限件数）
NOVEL_DB_QA_NUM_CTX = _s.NOVEL_DB_QA_NUM_CTX
NOVEL_DB_QA_EXPAND_ENABLED = _s.NOVEL_DB_QA_EXPAND_ENABLED
NOVEL_DB_QA_EXPAND_N = _s.NOVEL_DB_QA_EXPAND_N
NOVEL_DB_QA_EXPAND_MODEL = _s.NOVEL_DB_QA_EXPAND_MODEL
NOVEL_DB_QA_FULL_BOOK_MODE = _s.NOVEL_DB_QA_FULL_BOOK_MODE
NOVEL_DB_QA_FULL_BOOK_NUM_CTX = _s.NOVEL_DB_QA_FULL_BOOK_NUM_CTX
