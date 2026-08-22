"""Apple Siliconの公式`mlx_lm.server`を叩くOpenAI互換Backend。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator, Mapping
from typing import Any

from ._backend import LLMError
from ._json_output import normalize_json_events, normalize_json_events_async
from ._llama_server import LlamaServerBackend
from ._mlx import _apply_mlx_sampling_options


class MlxLmBackend(LlamaServerBackend):
    """`mlx_lm.server /v1/chat/completions`用Backend。"""

    _backend_name = "mlx_lm"
    _request_error_label = "MLX-LM server"

    def _build_body_from_messages(
        self,
        messages: list[Mapping[str, str]],
        *,
        model: str | None,
        options: dict[str, Any] | None,
        think: bool | None,
        format: str | None = None,
    ) -> dict[str, Any]:
        """MLX-LMのnested thinking契約とsampling名へ変換する。"""
        body = super()._build_body_from_messages(
            messages,
            model=model,
            options=options,
            think=think,
            format=format,
        )
        # mlx_lm.serverはresponse_formatを解釈しない。format=jsonは下流で
        # 完了後に限定正規化し、対応しているように見せかける送信を避ける。
        body.pop("response_format", None)
        _apply_mlx_sampling_options(
            body,
            defaults=self.config.default_options,
            options=options,
        )
        return body

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
                f"context resume is not supported with {self._backend_name} backend; "
                "use OllamaBackend if you need session continuation",
            )
        body = self._build_body(
            prompt,
            system=system,
            model=model,
            options=options,
            think=think,
            format=format,
        )
        events = super()._stream_body_sync(body, timeout=timeout)
        if format == "json":
            yield from normalize_json_events(events)
            return
        yield from events

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
                f"context resume is not supported with {self._backend_name} backend; "
                "use OllamaBackend if you need session continuation",
            )
        body = self._build_body(
            prompt,
            system=system,
            model=model,
            options=options,
            think=think,
            format=format,
        )
        events = super()._stream_body_async(body, timeout=timeout)
        if format == "json":
            async for event in normalize_json_events_async(events):
                yield event
            return
        async for event in events:
            yield event
