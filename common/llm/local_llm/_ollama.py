"""Ollama (`/api/generate`) を叩く Backend 実装。

Ollama 独自の `think=False` パラメータで thinking を抑制する。Qwen3.x で
`num_predict` を thinking ブロックに食い潰される事故を回避するため、
`BackendConfig.default_options` で `num_predict` を大きく取るのが推奨
（既定 8192）。

`context: list[int]` 引数で Ollama の生成コンテキストを引き継ぎセッション継続が可能
（CLI `ask.py --session` 用）。`LlamaServerBackend` は同等機能を持たないため
そちらでは `LLMError` を投げる。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Iterator
from typing import Any

from ._backend import _DEFAULT_THINK, Backend, LLMError


class OllamaBackend(Backend):
    """Ollama `/api/generate` を NDJSON ストリーミングで叩いて Ollama 形式 dict を返す。"""

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
        body = self._build_body(
            prompt, system=system, model=model, options=options,
            think=think, context=context, format=format,
        )
        req = urllib.request.Request(
            f"{self.config.base_url}/api/generate",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                req,
                timeout=timeout if timeout is not None else self.config.timeout,
            ) as resp:
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
        except urllib.error.URLError as e:
            raise LLMError(f"Ollama request failed: {e}") from e

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
        # httpx を遅延 import（同期しか使わない side では httpx インストール不要）
        import httpx  # noqa: PLC0415

        body = self._build_body(
            prompt, system=system, model=model, options=options,
            think=think, context=context, format=format,
        )
        timeout_sec = timeout if timeout is not None else float(self.config.timeout)
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_sec)) as client:
            async with client.stream(
                "POST",
                f"{self.config.base_url}/api/generate",
                json=body,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue

    def _build_body(
        self,
        prompt: str,
        *,
        system: str | None,
        model: str | None,
        options: dict[str, Any] | None,
        think: bool | None,
        context: list[int] | None,
        format: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model or self.config.model,
            "prompt": prompt,
            "stream": True,
            "think": _DEFAULT_THINK if think is None else think,
            "options": {**self.config.default_options, **(options or {})},
        }
        if system:
            body["system"] = system
        if context:
            body["context"] = context
        if format:
            # Ollama 仕様: body トップレベルの `format` キー (options.format ではない)
            body["format"] = format
        return body
