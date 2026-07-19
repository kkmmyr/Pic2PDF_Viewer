"""novel_db内のLLM呼び出しに渡すoptions辞書の共通ビルダー。"""

from __future__ import annotations

from typing import Any


def make_llm_options(
    *,
    temperature: float,
    num_predict: int,
    num_ctx: int,
    repeat_penalty: float | None = None,
) -> dict[str, Any]:
    """用途別の値をOllama互換optionsへ変換する。"""
    options: dict[str, Any] = {
        "temperature": temperature,
        "num_predict": num_predict,
        "num_ctx": num_ctx,
    }
    if repeat_penalty is not None:
        options["repeat_penalty"] = repeat_penalty
    return options
