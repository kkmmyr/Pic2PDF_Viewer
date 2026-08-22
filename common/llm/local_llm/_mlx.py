"""Apple Siliconの`mlx_vlm.server`を叩くOpenAI互換Backend。

SSEの通信・Ollama互換イベントへの正規化は`LlamaServerBackend`を再利用し、
MLX固有のthinking指定とsampling option名だけを変換する。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._backend import _DEFAULT_THINK
from ._llama_server import LlamaServerBackend


def _apply_mlx_sampling_options(
    body: dict[str, Any],
    *,
    defaults: Mapping[str, Any],
    options: dict[str, Any] | None,
) -> None:
    """Ollama互換sampling名をMLX系serverのrequest名へ変換する。"""
    merged = {**defaults, **(options or {})}
    direct_options = (
        "top_k",
        "min_p",
        "seed",
        "presence_penalty",
        "frequency_penalty",
        "repetition_context_size",
        "presence_context_size",
        "frequency_context_size",
    )
    for key in direct_options:
        if key in merged:
            body[key] = merged[key]

    if "repeat_last_n" in merged:
        body["repetition_context_size"] = merged["repeat_last_n"]
    if "repeat_penalty" in merged:
        body["repetition_penalty"] = merged["repeat_penalty"]
    if "repetition_penalty" in merged:
        body["repetition_penalty"] = merged["repetition_penalty"]


class MlxBackend(LlamaServerBackend):
    """`mlx_vlm.server /v1/chat/completions`用Backend。"""

    _backend_name = "mlx"
    _request_error_label = "MLX server"

    def _build_body_from_messages(
        self,
        messages: list[Mapping[str, str]],
        *,
        model: str | None,
        options: dict[str, Any] | None,
        think: bool | None,
        format: str | None = None,
    ) -> dict[str, Any]:
        """Ollama互換optionをMLX serverのrequest bodyへ変換する。"""
        body = super()._build_body_from_messages(
            messages,
            model=model,
            options=options,
            think=think,
            format=format,
        )
        body.pop("chat_template_kwargs", None)
        body["enable_thinking"] = bool(think) if think is not None else _DEFAULT_THINK

        _apply_mlx_sampling_options(
            body,
            defaults=self.config.default_options,
            options=options,
        )
        return body
