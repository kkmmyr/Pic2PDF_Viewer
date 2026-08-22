"""Backend 抽象 + 共通設定 + 例外。

Backend は 2 つの抽象メソッド (`stream_ask` / `astream_ask`) を実装するだけで
集約版 (`ask` / `aask`) が自動的に動く。新バックエンドを追加する際は本ファイルに
触れる必要はなく、新しい `Backend` サブクラスを 1 つ作るだけで済む。

設定は `BackendConfig` dataclass を引数渡しする方式に統一しており、
環境変数を読むのは `_factory.backend_from_env()` の 1 箇所のみ。
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any


class LLMError(RuntimeError):
    """バックエンド呼び出し失敗時に投げる。

    Ollama / llama-server / MLX接続失敗、サポート外引数（OpenAI互換backendでcontext渡し
    等）、未知の backend 種別などを区別せず本クラスで投げる。
    """


# Qwen3.x で PoC 検証済みの安全側パラメータ。
# `num_predict` を thinking ブロックに食い潰される事故を避けるため余裕を持たせる
# （詳細は ADR-0007 / `小説RAG_技術知見.md §1`）。
_DEFAULT_OPTIONS: Mapping[str, Any] = {
    "temperature": 0.2,
    "repeat_penalty": 1.2,
    "num_predict": 8192,
    "num_ctx": 8192,
}

# Qwen3.x は thinking モデル。stream=True / think=False を強制（地雷回避）。
# 利用側で `think=True` を渡せば個別に上書き可能。
_DEFAULT_THINK = False


@dataclass(frozen=True)
class BackendConfig:
    """LLM バックエンド 1 系統の接続設定。

    `base_url` 以外はすべて呼び出し時 (`stream_ask` の引数) で個別上書き可能。
    `default_options` は `stream_ask` の `options` 引数とマージされ、呼び出し側
    `options` が優先される。
    """

    base_url: str
    model: str = "qwen3.6:35b-a3b"
    timeout: int = 600
    default_options: Mapping[str, Any] = field(
        default_factory=lambda: dict(_DEFAULT_OPTIONS),
    )


class Backend(abc.ABC):
    """同期 + async ストリーミングと、その集約版を提供する LLM バックエンド。

    具体実装は`OllamaBackend` / `LlamaServerBackend` / `MlxBackend` /
    `MlxLmBackend` / `MlxDsparkBackend`。
    新バックエンド追加時は `stream_ask` / `astream_ask` の 2 抽象メソッドだけ
    実装すれば、`ask` / `aask` は本クラスのデフォルト実装が利用される。

    yield されるイベントはすべて Ollama 互換の dict 形式に正規化されている
    （`response` / `done` / `done_reason` / `prompt_eval_count` / `eval_count`）。
    """

    config: BackendConfig

    def __init__(self, config: BackendConfig) -> None:
        self.config = config

    @abc.abstractmethod
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
        """同期ストリーミング。Ollama 形式 dict のイベントを yield する。

        最終イベントには `done=True` / `done_reason` / `eval_count` 等が含まれる。
        `context` は Ollama backend のみセッション継続用に使える
        （llama-server / MLX backendでは`LLMError`を投げる）。
        `format` は LLM 出力フォーマットの強制（現状 `"json"` のみサポート）。
        Ollamaではbodyトップレベル`format`キーへ、llama-server / MLX-VLMでは
        OpenAI 互換 `response_format={"type": "json_object"}` へ変換される。
        MLX-LMではserverが未対応のため、完了後に限定的なfail-closed正規化を行う。
        """

    @abc.abstractmethod
    def astream_ask(
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
        """async ストリーミング。FastAPI SSE 等から利用。

        サブクラスは `async def` で実装し本文で `yield` する
        （= async generator）。シグネチャ上は `AsyncIterator` を返す扱い。
        `format` 引数の仕様は `stream_ask` と同じ。
        """

    def ask(self, prompt: str, **kw: Any) -> str:
        """同期で完全な response 文字列を返す（ストリームを内部集約）。"""
        parts: list[str] = []
        for event in self.stream_ask(prompt, **kw):
            if event.get("response"):
                parts.append(event["response"])
            if event.get("done"):
                break
        return "".join(parts)

    async def aask(self, prompt: str, **kw: Any) -> str:
        """async で完全な response 文字列を返す。"""
        parts: list[str] = []
        async for event in self.astream_ask(prompt, **kw):
            if event.get("response"):
                parts.append(event["response"])
            if event.get("done"):
                break
        return "".join(parts)

    # ------------------------------------------------------------------
    # Multi-turn chat API（任意実装）
    # ------------------------------------------------------------------
    #
    # OpenAI 互換 `messages: list[{role, content}]` を受け取って同じ Ollama 形式
    # の dict イベントを yield する。`stream_ask` の system + 単発 prompt とは
    # 別の入口として、サブクラスが必要に応じて override する。デフォルト実装は
    # `NotImplementedError` を投げる（chat 非対応バックエンドはこのまま）。
    #
    # ストリームイベントの正規化規約は `stream_ask` と同一（`response` /
    # `done` / `done_reason` / `eval_count` / `prompt_eval_count`）。

    def stream_chat(
        self,
        messages: list[Mapping[str, str]],
        *,
        model: str | None = None,
        options: dict[str, Any] | None = None,
        think: bool | None = None,
        timeout: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """同期 multi-turn chat ストリーミング。デフォルトは未対応。"""
        raise NotImplementedError(
            f"{type(self).__name__} does not support multi-turn chat; "
            f"use stream_ask for single-turn",
        )

    def astream_chat(
        self,
        messages: list[Mapping[str, str]],
        *,
        model: str | None = None,
        options: dict[str, Any] | None = None,
        think: bool | None = None,
        timeout: float | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """async multi-turn chat ストリーミング。デフォルトは未対応。"""
        raise NotImplementedError(
            f"{type(self).__name__} does not support multi-turn chat; "
            f"use astream_ask for single-turn",
        )
