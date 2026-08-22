"""Apple Siliconの`mlx-dspark` OpenAI互換serverを叩くBackend。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._mlx_lm import MlxLmBackend


class MlxDsparkBackend(MlxLmBackend):
    """`mlx-dspark /v1/chat/completions`用Backend。

    mlx-dsparkは`chat_template_kwargs`と標準OpenAIのsampling項目を受理するが、
    `response_format`を生成制約として扱わない。そのため、nested thinking契約と
    `MlxLmBackend`の限定JSON adapterをそのまま再利用する。
    """

    _backend_name = "mlx_dspark"
    _request_error_label = "MLX-dspark server"

    def _build_body_from_messages(
        self,
        messages: list[Mapping[str, str]],
        *,
        model: str | None,
        options: dict[str, Any] | None,
        think: bool | None,
        format: str | None = None,
    ) -> dict[str, Any]:
        """Drop sampling fields that mlx-dspark does not implement."""
        body = super()._build_body_from_messages(
            messages,
            model=model,
            options=options,
            think=think,
            format=format,
        )
        for key in (
            "min_p",
            "repetition_penalty",
            "repetition_context_size",
            "presence_context_size",
            "frequency_context_size",
        ):
            body.pop(key, None)
        return body
