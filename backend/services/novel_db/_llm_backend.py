"""共通 LLM パッケージ (`local_llm`) の sys.path 注入 + Qwen 用 Backend ファクトリ。

novel_db 配下の LLM 利用箇所は本ファイル経由で `local_llm` の Backend を取得する。
sys.path 注入と Backend 構築の責務をここに集約することで、各 service ファイル
（llm.py / summarizer.py 等）から「外部モジュールへの依存」が見えにくくなる
弊害を避ける（明示的に `from ._llm_backend import build_qwen_backend` と書く）。

config.py の `NOVEL_DB_LLM_BACKEND` を見て `LlamaServerBackend`（既定）or
`OllamaBackend`（rollback 用）を作る。`build_qwen_backend()` は呼び出すたびに
新しいインスタンスを返すので、利用側 (llm.py / summarizer.py) で各自モジュール
レベル変数に保持して使い回す。Backend は完全に stateless （frozen dataclass の
config を持つだけ）なので複数インスタンスを作っても害はない。
"""
from __future__ import annotations

import sys

# 共通 LLM パッケージへのパスを追加（プロセスで 1 度だけ）
_LLM_PKG_DIR = r"D:\61.tool\common\llm"
if _LLM_PKG_DIR not in sys.path:
    sys.path.insert(0, _LLM_PKG_DIR)

from local_llm import (  # noqa: E402
    Backend,
    BackendConfig,
    LlamaServerBackend,
    LLMError,
    OllamaBackend,
)

import config  # noqa: E402


def build_qwen_backend() -> Backend:
    """`config.py` の `NOVEL_DB_*` 値から Qwen 用 `Backend` を 1 つ構築する。

    `NOVEL_DB_LLM_BACKEND='llama_server'`（既定）→ `LlamaServerBackend`
    `NOVEL_DB_LLM_BACKEND='ollama'` → `OllamaBackend`（rollback 用）

    base_url は backend 種別に応じて使い分ける。model はどちらでも同じ
    `NOVEL_DB_LLM_MODEL`（既定 `qwen3.6-iq4xs`）。

    config の値は呼び出し時に参照する（`from config import X` ではなく
    `config.X`）。これにより monkeypatch で上書きしたテストが reload なしで
    動作し、後続テストへの状態漏れを防げる。
    """
    if config.NOVEL_DB_LLM_BACKEND == "llama_server":
        return LlamaServerBackend(BackendConfig(
            base_url=config.NOVEL_DB_LLAMA_SERVER_URL,
            model=config.NOVEL_DB_LLM_MODEL,
        ))
    if config.NOVEL_DB_LLM_BACKEND == "ollama":
        return OllamaBackend(BackendConfig(
            base_url=config.NOVEL_DB_OLLAMA_BASE_URL,
            model=config.NOVEL_DB_LLM_MODEL,
        ))
    raise LLMError(
        f"unknown NOVEL_DB_LLM_BACKEND: {config.NOVEL_DB_LLM_BACKEND}",
    )
