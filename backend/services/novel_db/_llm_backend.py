"""既存importを維持するLLM backend互換facade。

新規application codeは ``llm_provider`` を参照し、必要なら
``NovelLlmProvider`` を明示注入する。
"""

from .llm_provider import get_llm_provider

_PROVIDER = get_llm_provider()

QWEN_BACKEND = _PROVIDER.qwen
GEMMA_BACKEND = _PROVIDER.gemma
QUERY_BACKEND = _PROVIDER.query
VERIFIER_BACKEND = _PROVIDER.verifier

__all__ = ["GEMMA_BACKEND", "QUERY_BACKEND", "QWEN_BACKEND", "VERIFIER_BACKEND"]
