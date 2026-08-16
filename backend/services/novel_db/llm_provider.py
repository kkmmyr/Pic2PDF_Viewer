"""Novel RAGで使用する用途別LLM backendのprovider。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from local_llm import Backend, BackendConfig, LlamaServerBackend, LLMError, OllamaBackend

import config


@dataclass(frozen=True, slots=True)
class NovelLlmProvider:
    """Application serviceへ注入する用途別backend集合。"""

    qwen: Backend
    gemma: Backend
    query: Backend
    verifier: Backend


def build_llm_provider() -> NovelLlmProvider:
    """現在設定からproviderを構築する。"""
    if config.NOVEL_DB_LLM_BACKEND != "llama_server":
        raise LLMError(
            f"unknown NOVEL_DB_LLM_BACKEND: {config.NOVEL_DB_LLM_BACKEND} (supported: 'llama_server')",
        )

    qwen: Backend = LlamaServerBackend(
        BackendConfig(
            base_url=config.NOVEL_DB_LLAMA_SERVER_URL,
            model=config.NOVEL_DB_LLM_MODEL,
        )
    )
    gemma: Backend
    if config.NOVEL_DB_GEMMA_BACKEND == "qwen":
        gemma = qwen
    else:
        gemma = OllamaBackend(
            BackendConfig(
                base_url=config.NOVEL_DB_OLLAMA_BASE_URL,
                model=config.NOVEL_DB_CHAR_EXTRACT_MODEL,
                timeout=120,
            )
        )

    query: Backend = OllamaBackend(
        BackendConfig(
            base_url=config.NOVEL_DB_OLLAMA_BASE_URL,
            model=config.NOVEL_DB_QA_EXPAND_MODEL,
            timeout=60,
        )
    )

    if config.NOVEL_DB_VERIFIER_BACKEND == "qwen":
        verifier = qwen
    elif config.NOVEL_DB_VERIFIER_BACKEND == "ollama":
        if not config.NOVEL_DB_VERIFIER_MODEL:
            raise LLMError("NOVEL_DB_VERIFIER_MODEL is required for verifier backend 'ollama'")
        verifier = OllamaBackend(
            BackendConfig(
                base_url=config.NOVEL_DB_OLLAMA_BASE_URL,
                model=config.NOVEL_DB_VERIFIER_MODEL,
            )
        )
    elif config.NOVEL_DB_VERIFIER_BACKEND == "llama_server":
        if not config.NOVEL_DB_VERIFIER_MODEL:
            raise LLMError("NOVEL_DB_VERIFIER_MODEL is required for verifier backend 'llama_server'")
        verifier = LlamaServerBackend(
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

    return NovelLlmProvider(qwen=qwen, gemma=gemma, query=query, verifier=verifier)


@lru_cache(maxsize=1)
def get_llm_provider() -> NovelLlmProvider:
    """既定providerをprocess内で一度だけ構築して返す。"""
    return build_llm_provider()
