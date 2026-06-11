"""llama.cpp `llama-server` (OpenAI 互換 `/v1/chat/completions`) を叩く Backend 実装。

`chat_template_kwargs.enable_thinking=False` で thinking を抑制する
（Ollama 独自の `think=False` の代替、`--jinja` 起動必須）。
`stream_options.include_usage=True` で末尾 usage チャンクを取得し
`prompt_eval_count` / `eval_count` を Ollama 形式に正規化して yield する。

`context` 引数（Ollama のセッション継続）には対応しない (`LLMError`)。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Iterator, Mapping
from typing import Any

from ._backend import _DEFAULT_THINK, Backend, LLMError
from ._sse import convert_openai_chunk, fallback_done_event


class LlamaServerBackend(Backend):
    """llama-server `/v1/chat/completions` を OpenAI SSE で叩き、Ollama 形式 dict に正規化。"""

    def stream_ask(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        options: dict[str, Any] | None = None,
        think: bool | None = None,
        timeout: int | None = None,
        context: list[int] | None = None,
        format: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        if context:
            raise LLMError(
                "context resume is not supported with llama_server backend; "
                "use OllamaBackend if you need session continuation",
            )
        body = self._build_body(
            prompt, system=system, model=model, options=options, think=think,
            format=format,
        )
        yield from self._stream_body_sync(body, timeout=timeout)

    async def astream_ask(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        options: dict[str, Any] | None = None,
        think: bool | None = None,
        timeout: float | None = None,
        context: list[int] | None = None,
        format: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        if context:
            raise LLMError(
                "context resume is not supported with llama_server backend; "
                "use OllamaBackend if you need session continuation",
            )
        body = self._build_body(
            prompt, system=system, model=model, options=options, think=think,
            format=format,
        )
        async for event in self._stream_body_async(body, timeout=timeout):
            yield event

    def _build_body(
        self,
        prompt: str,
        *,
        system: str | None,
        model: str | None,
        options: dict[str, Any] | None,
        think: bool | None,
        format: str | None = None,
    ) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self._build_body_from_messages(
            messages, model=model, options=options, think=think, format=format,
        )

    def _build_body_from_messages(
        self,
        messages: list[Mapping[str, str]],
        *,
        model: str | None,
        options: dict[str, Any] | None,
        think: bool | None,
        format: str | None = None,
    ) -> dict[str, Any]:
        """multi-turn 用 body 組立。`stream_chat` から `messages` 受け取りで利用。"""
        merged = {**self.config.default_options, **(options or {})}
        body: dict[str, Any] = {
            # llama-server は無視するが OpenAI API 仕様で model キーは必須
            "model": model or self.config.model,
            "messages": [dict(m) for m in messages],
            "stream": True,
            # include_usage=true で末尾に usage 専用チャンクが届く
            "stream_options": {"include_usage": True},
            "max_tokens": merged.get("num_predict", 4096),
            "temperature": merged.get("temperature", 0.2),
            "chat_template_kwargs": {
                "enable_thinking": (
                    bool(think) if think is not None else _DEFAULT_THINK
                ),
            },
        }
        # OpenAI API では top_p は省略可。指定された場合のみボディに載せる
        if "top_p" in merged:
            body["top_p"] = merged["top_p"]
        if format is not None:
            # OpenAI 互換 response_format に変換。現状は "json" のみサポート。
            if format == "json":
                body["response_format"] = {"type": "json_object"}
            else:
                raise LLMError(
                    f"format={format!r} is not supported by LlamaServerBackend; "
                    f"only 'json' is implemented",
                )
        return body

    # ------------------------------------------------------------------
    # Multi-turn chat
    # ------------------------------------------------------------------

    def stream_chat(
        self,
        messages: list[Mapping[str, str]],
        *,
        model: str | None = None,
        options: dict[str, Any] | None = None,
        think: bool | None = None,
        timeout: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """OpenAI 互換 messages を直接渡して同期ストリーミングする。

        `messages` の各要素は `{"role": "user"|"assistant"|"system", "content": ...}`。
        role の順序検証は呼び出し側責務（chat-template はそのまま messages を流す）。
        """
        body = self._build_body_from_messages(
            messages, model=model, options=options, think=think,
        )
        yield from self._stream_body_sync(body, timeout=timeout)

    async def astream_chat(
        self,
        messages: list[Mapping[str, str]],
        *,
        model: str | None = None,
        options: dict[str, Any] | None = None,
        think: bool | None = None,
        timeout: float | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """OpenAI 互換 messages を直接渡して async ストリーミングする。"""
        body = self._build_body_from_messages(
            messages, model=model, options=options, think=think,
        )
        async for event in self._stream_body_async(body, timeout=timeout):
            yield event

    # ------------------------------------------------------------------
    # 共通: body → イベントストリーム
    # ------------------------------------------------------------------

    def _stream_body_sync(
        self, body: dict[str, Any], *, timeout: int | None,
    ) -> Iterator[dict[str, Any]]:
        req = urllib.request.Request(
            f"{self.config.base_url}/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                req,
                timeout=timeout if timeout is not None else self.config.timeout,
            ) as resp:
                pending_finish: str | None = None
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[len("data:"):].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    event = convert_openai_chunk(chunk)
                    if event is None:
                        continue
                    if "_finish" in event:
                        pending_finish = event.pop("_finish")
                        if event.get("response"):
                            yield event
                        continue
                    yield event
                    if event.get("done"):
                        pending_finish = None
                if pending_finish is not None:
                    yield fallback_done_event(pending_finish)
        except urllib.error.URLError as e:
            raise LLMError(f"llama-server request failed: {e}") from e

    async def _stream_body_async(
        self, body: dict[str, Any], *, timeout: float | None,
    ) -> AsyncIterator[dict[str, Any]]:
        import httpx  # noqa: PLC0415

        timeout_sec = timeout if timeout is not None else float(self.config.timeout)
        pending_finish: str | None = None
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_sec)) as client:
            async with client.stream(
                "POST",
                f"{self.config.base_url}/v1/chat/completions",
                json=body,
                headers={"Accept": "text/event-stream"},
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[len("data:"):].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    event = convert_openai_chunk(chunk)
                    if event is None:
                        continue
                    if "_finish" in event:
                        pending_finish = event.pop("_finish")
                        if event.get("response"):
                            yield event
                        continue
                    yield event
                    if event.get("done"):
                        pending_finish = None
        if pending_finish is not None:
            yield fallback_done_event(pending_finish)
