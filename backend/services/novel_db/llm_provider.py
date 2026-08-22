"""Novel RAGで使用する用途別LLM backendのprovider。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from local_llm import Backend, BackendConfig, LlamaServerBackend, LLMError, OllamaBackend

import config

_QWEN_MLX_DEFAULT_OPTIONS = {
    "temperature": 0.2,
    "repeat_penalty": 1.2,
    "num_predict": 8192,
    "num_ctx": 8192,
    "top_p": 0.95,
    "top_k": 20,
    "min_p": 0.0,
    "presence_penalty": 1.5,
}
_GEMMA_MLX_DEFAULT_OPTIONS = {
    "temperature": 0.2,
    "repeat_penalty": 1.2,
    "num_predict": 8192,
    "num_ctx": 8192,
    "top_p": 0.95,
    "top_k": 64,
}


def _build_mlx_backend(backend_config: BackendConfig) -> Backend:
    """MLX選択時だけ実装をimportし、既定Linux経路との互換性を保つ。"""
    from local_llm import MlxBackend

    return MlxBackend(backend_config)


@dataclass(frozen=True, slots=True)
class NovelLlmProvider:
    """Application serviceへ注入する用途別backend集合。"""

    qwen: Backend
    gemma: Backend
    query: Backend
    verifier: Backend


def build_llm_provider() -> NovelLlmProvider:
    """現在設定からproviderを構築する。"""
    if config.NOVEL_DB_LLM_BACKEND == "llama_server":
        qwen: Backend = LlamaServerBackend(
            BackendConfig(
                base_url=config.NOVEL_DB_LLAMA_SERVER_URL,
                model=config.NOVEL_DB_LLM_MODEL,
            )
        )
    elif config.NOVEL_DB_LLM_BACKEND == "mlx":
        qwen = _build_mlx_backend(
            BackendConfig(
                base_url=config.NOVEL_DB_MLX_BASE_URL,
                model=config.NOVEL_DB_LLM_MODEL,
                default_options=_QWEN_MLX_DEFAULT_OPTIONS,
            )
        )
    else:
        raise LLMError(
            f"unknown NOVEL_DB_LLM_BACKEND: {config.NOVEL_DB_LLM_BACKEND} (supported: 'llama_server', 'mlx')",
        )

    gemma: Backend
    if config.NOVEL_DB_GEMMA_BACKEND == "qwen":
        gemma = qwen
    elif config.NOVEL_DB_GEMMA_BACKEND == "ollama":
        gemma = OllamaBackend(
            BackendConfig(
                base_url=config.NOVEL_DB_OLLAMA_BASE_URL,
                model=config.NOVEL_DB_CHAR_EXTRACT_MODEL,
                timeout=120,
            )
        )
    elif config.NOVEL_DB_GEMMA_BACKEND == "mlx":
        gemma = _build_mlx_backend(
            BackendConfig(
                base_url=config.NOVEL_DB_MLX_BASE_URL,
                model=config.NOVEL_DB_CHAR_EXTRACT_MODEL,
                timeout=120,
                default_options=_GEMMA_MLX_DEFAULT_OPTIONS,
            )
        )
    else:
        raise LLMError(
            f"unknown NOVEL_DB_GEMMA_BACKEND: {config.NOVEL_DB_GEMMA_BACKEND} (supported: 'ollama', 'qwen', 'mlx')",
        )

    query: Backend
    if config.NOVEL_DB_GEMMA_BACKEND == "mlx":
        query = _build_mlx_backend(
            BackendConfig(
                base_url=config.NOVEL_DB_MLX_BASE_URL,
                model=config.NOVEL_DB_QA_EXPAND_MODEL,
                timeout=60,
                default_options=_GEMMA_MLX_DEFAULT_OPTIONS,
            )
        )
    else:
        query = OllamaBackend(
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
    elif config.NOVEL_DB_VERIFIER_BACKEND == "mlx":
        if not config.NOVEL_DB_VERIFIER_MODEL:
            raise LLMError("NOVEL_DB_VERIFIER_MODEL is required for verifier backend 'mlx'")
        verifier = _build_mlx_backend(
            BackendConfig(
                base_url=config.NOVEL_DB_VERIFIER_BASE_URL,
                model=config.NOVEL_DB_VERIFIER_MODEL,
                default_options=_QWEN_MLX_DEFAULT_OPTIONS,
            )
        )
    else:
        raise LLMError(
            f"unknown NOVEL_DB_VERIFIER_BACKEND: {config.NOVEL_DB_VERIFIER_BACKEND} "
            "(supported: 'qwen', 'ollama', 'llama_server', 'mlx')",
        )

    return NovelLlmProvider(qwen=qwen, gemma=gemma, query=query, verifier=verifier)


@lru_cache(maxsize=1)
def get_llm_provider() -> NovelLlmProvider:
    """既定providerをprocess内で一度だけ構築して返す。"""
    return build_llm_provider()
