"""MLX-LMのJSON出力を限定的に正規化するfail-closed adapter。"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterable, AsyncIterator, Iterable, Iterator
from typing import Any

from ._backend import LLMError

_MAX_JSON_CHARS = 1024 * 1024
_JSON_FENCE = re.compile(
    r"\A[\t\r\n ]*```json[\t ]*\r?\n(?P<body>.*?)\r?\n```[\t\r\n ]*\Z",
    re.DOTALL,
)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_non_finite(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def normalize_json_object(text: str, *, max_chars: int = _MAX_JSON_CHARS) -> str:
    """厳格なJSON objectか、単独の小文字`json` fenceだけを正規化する。"""
    if len(text) > max_chars:
        raise LLMError(
            f"MLX-LM JSON response exceeds {max_chars} characters",
        )

    stripped = text.strip()
    fence = _JSON_FENCE.fullmatch(text)
    candidate = fence.group("body") if fence is not None else stripped

    try:
        value = json.loads(
            candidate,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMError(
            "MLX-LM JSON response is neither a strict object nor one isolated "
            "lowercase json fence",
        ) from exc

    if not isinstance(value, dict):
        raise LLMError("MLX-LM JSON response must be an object")

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def normalize_json_events(
    events: Iterable[dict[str, Any]],
    *,
    max_chars: int = _MAX_JSON_CHARS,
) -> Iterator[dict[str, Any]]:
    """完了・自然停止・JSON全体を検証してから正規化イベントを返す。"""
    parts: list[str] = []
    total_chars = 0
    done_event: dict[str, Any] | None = None

    for event in events:
        if done_event is not None:
            raise LLMError("MLX-LM stream emitted data after the done event")
        if event.get("done"):
            done_event = dict(event)
            continue

        response = event.get("response", "")
        if not isinstance(response, str):
            raise LLMError("MLX-LM stream emitted a non-string response")
        total_chars += len(response)
        if total_chars > max_chars:
            raise LLMError(
                f"MLX-LM JSON response exceeds {max_chars} characters",
            )
        parts.append(response)

    if done_event is None:
        raise LLMError("MLX-LM JSON stream ended without a done event")
    if done_event.get("done_reason") != "stop":
        raise LLMError(
            "MLX-LM JSON stream did not finish naturally: "
            f"{done_event.get('done_reason')!r}",
        )

    normalized = normalize_json_object("".join(parts), max_chars=max_chars)
    yield {"response": normalized, "done": False}
    done_event["response"] = ""
    yield done_event


async def normalize_json_events_async(
    events: AsyncIterable[dict[str, Any]],
    *,
    max_chars: int = _MAX_JSON_CHARS,
) -> AsyncIterator[dict[str, Any]]:
    """async stream版。検証完了までは呼び出し側へ部分応答を公開しない。"""
    parts: list[str] = []
    total_chars = 0
    done_event: dict[str, Any] | None = None

    async for event in events:
        if done_event is not None:
            raise LLMError("MLX-LM stream emitted data after the done event")
        if event.get("done"):
            done_event = dict(event)
            continue

        response = event.get("response", "")
        if not isinstance(response, str):
            raise LLMError("MLX-LM stream emitted a non-string response")
        total_chars += len(response)
        if total_chars > max_chars:
            raise LLMError(
                f"MLX-LM JSON response exceeds {max_chars} characters",
            )
        parts.append(response)

    if done_event is None:
        raise LLMError("MLX-LM JSON stream ended without a done event")
    if done_event.get("done_reason") != "stop":
        raise LLMError(
            "MLX-LM JSON stream did not finish naturally: "
            f"{done_event.get('done_reason')!r}",
        )

    normalized = normalize_json_object("".join(parts), max_chars=max_chars)
    yield {"response": normalized, "done": False}
    done_event["response"] = ""
    yield done_event
