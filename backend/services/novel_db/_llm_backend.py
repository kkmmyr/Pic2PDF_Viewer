"""novel_db サービス全体で共有する LLM Backend シングルトン。

各サービスモジュールは _BACKEND を個別に構築せず、ここから import して使う。

- QWEN_BACKEND  : Qwen 重量モデル（QA / 書籍サマリ / キャラサマリ / 関係グラフ）
- GEMMA_BACKEND : Gemma 軽量モデル（キャラ抽出 / チャンクコンテキスト生成）
- QUERY_BACKEND : Query Expansion 専用（timeout 短め）
- VERIFIER_BACKEND: 要約根拠検証（既定はQwen直列再利用、別backendへ切替可）
"""

from __future__ import annotations

from local_llm import Backend, BackendConfig, LlamaServerBackend, LLMError, OllamaBackend

import config

# Qwen 重量モデル（llama_server 一択。config.NOVEL_DB_LLM_BACKEND が未知値なら即 fail）
if config.NOVEL_DB_LLM_BACKEND == "llama_server":
    QWEN_BACKEND: Backend = LlamaServerBackend(
        BackendConfig(
            base_url=config.NOVEL_DB_LLAMA_SERVER_URL,
            model=config.NOVEL_DB_LLM_MODEL,
        )
    )
else:
    raise LLMError(
        f"unknown NOVEL_DB_LLM_BACKEND: {config.NOVEL_DB_LLM_BACKEND} (supported: 'llama_server')",
    )

# Gemma 軽量モデル（ollama 既定 / "qwen" 設定時は QWEN_BACKEND を流用）
if config.NOVEL_DB_GEMMA_BACKEND == "qwen":
    GEMMA_BACKEND: Backend = QWEN_BACKEND
else:
    GEMMA_BACKEND = OllamaBackend(
        BackendConfig(
            base_url=config.NOVEL_DB_OLLAMA_BASE_URL,
            model=config.NOVEL_DB_CHAR_EXTRACT_MODEL,
            timeout=120,
        )
    )

# Query Expansion 専用（gemma4:e4b / timeout 60 秒）
QUERY_BACKEND: Backend = OllamaBackend(
    BackendConfig(
        base_url=config.NOVEL_DB_OLLAMA_BASE_URL,
        model=config.NOVEL_DB_QA_EXPAND_MODEL,
        timeout=60,
    )
)

if config.NOVEL_DB_VERIFIER_BACKEND == "qwen":
    VERIFIER_BACKEND: Backend = QWEN_BACKEND
elif config.NOVEL_DB_VERIFIER_BACKEND == "ollama":
    if not config.NOVEL_DB_VERIFIER_MODEL:
        raise LLMError("NOVEL_DB_VERIFIER_MODEL is required for verifier backend 'ollama'")
    VERIFIER_BACKEND = OllamaBackend(
        BackendConfig(
            base_url=config.NOVEL_DB_OLLAMA_BASE_URL,
            model=config.NOVEL_DB_VERIFIER_MODEL,
        )
    )
elif config.NOVEL_DB_VERIFIER_BACKEND == "llama_server":
    if not config.NOVEL_DB_VERIFIER_MODEL:
        raise LLMError("NOVEL_DB_VERIFIER_MODEL is required for verifier backend 'llama_server'")
    VERIFIER_BACKEND = LlamaServerBackend(
        BackendConfig(
            base_url=config.NOVEL_DB_VERIFIER_BASE_URL,
            model=config.NOVEL_DB_VERIFIER_MODEL,
        )
    )
else:
    raise LLMError(
        f"unknown NOVEL_DB_VERIFIER_BACKEND: {config.NOVEL_DB_VERIFIER_BACKEND} "
        "(supported: 'qwen', 'ollama', 'llama_server')",
    )
