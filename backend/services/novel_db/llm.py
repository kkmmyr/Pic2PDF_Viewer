"""Qwen LLM への SSE ストリーミング呼び出し（QA / chat エンドポイント用）。

詳細は docs/design/詳細設計/機能別/小説RAG_検索QA設計.md §5 と
ADR-0009（推論バックエンド切替）。

プロンプト組み立てロジックは prompt_builder.py に分離した。
このモジュールは LLM 呼び出しとパラメータ定数のみを担う。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from config import NOVEL_DB_LLM_MODEL, NOVEL_DB_QA_NUM_CTX

from ._llm_backend import QWEN_BACKEND

# PoC で確定した QA 用 LLM パラメータ。num_ctx は config 化されており、B-13 段階 A〜C で
# 段階拡大（既定 32768）。
# 注意: llama-server バックエンドでは num_ctx は起動時 `-c` で決まるため、ここで
# 渡しても無視される（指定しても害はない）。env が llama_server の場合は
# start-qwen-server.bat 側で `-c 131072` を変更すること。
LLM_OPTIONS: dict[str, Any] = {
    "temperature": 0.2,
    "repeat_penalty": 1.2,
    "num_predict": 4096,
    "num_ctx": NOVEL_DB_QA_NUM_CTX,
}


async def _astream_ask(
    prompt: str,
    *,
    model: str | None = None,
    options: dict | None = None,
    timeout: float | None = None,
) -> AsyncIterator[dict]:
    """共通 Backend に委譲する thin wrapper。テストでは monkeypatch で差し替え可能。

    `stream_qa` から呼ばれる単一の入口。利用側は `_astream_ask` を直接 mock
    することで、Backend 実体（HTTP）を介さずにテストできる。
    """
    async for event in QWEN_BACKEND.astream_ask(
        prompt,
        model=model,
        options=options,
        timeout=timeout,
    ):
        yield event


async def stream_qa(
    prompt: str,
    *,
    model: str = NOVEL_DB_LLM_MODEL,
    options: dict | None = None,
    timeout: float = 600.0,
) -> AsyncIterator[dict]:
    """Qwen に stream=True で投げ、各イベントを yield する。

    実体は `_llm_backend.QWEN_BACKEND.astream_ask` を呼ぶだけ。
    バックエンド分岐（Ollama / llama-server）、thinking 抑制、SSE→Ollama 形式の
    正規化はすべて共通モジュール (`local_llm`) 側に集約している。
    """
    async for event in _astream_ask(
        prompt,
        model=model,
        options=options or LLM_OPTIONS,
        timeout=timeout,
    ):
        yield event


async def astream_chat(
    messages: list[dict],
    *,
    model: str | None = None,
    options: dict | None = None,
    timeout: float | None = None,
) -> AsyncIterator[dict]:
    """共通 Backend.astream_chat への thin wrapper。テストでは monkeypatch で差替可能。"""
    async for event in QWEN_BACKEND.astream_chat(
        messages,  # type: ignore[arg-type]
        model=model,
        options=options,
        timeout=timeout,
    ):
        yield event


async def stream_chat(
    messages: list[dict],
    *,
    model: str = NOVEL_DB_LLM_MODEL,
    options: dict | None = None,
    timeout: float = 600.0,
) -> AsyncIterator[dict]:
    """OpenAI 互換 messages を直接 LLM に流す（multi-turn）。

    実体は `_BACKEND.astream_chat`（`LlamaServerBackend` 専用、Ollama は
    NotImplementedError）。バックエンド側の thinking 抑制 + SSE 正規化は
    `local_llm` に委譲する。
    """
    async for event in astream_chat(
        messages,
        model=model,
        options=options or LLM_OPTIONS,
        timeout=timeout,
    ):
        yield event
