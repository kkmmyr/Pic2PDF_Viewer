"""`mlx-dspark`用Backendのrequest契約回帰テスト。"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from local_llm import BackendConfig, LLMError, MlxDsparkBackend


def _sse_response(chunks: list[dict[str, Any] | str]) -> MagicMock:
    lines: list[bytes] = []
    for chunk in chunks:
        payload = chunk if isinstance(chunk, str) else json.dumps(chunk)
        lines.extend((f"data: {payload}\n".encode(), b"\n"))
    response = MagicMock()
    response.__iter__ = lambda self: iter(lines)
    response.__enter__ = lambda self: response
    response.__exit__ = lambda self, *args: None
    return response


def test_uses_nested_thinking_and_omits_response_format() -> None:
    backend = MlxDsparkBackend(
        BackendConfig(
            base_url="http://test-mlx-dspark:11439",
            model="/models/qwen3.8",
            default_options={
                "temperature": 0.2,
                "repeat_penalty": 1.2,
                "num_predict": 8192,
                "num_ctx": 131072,
                "top_p": 0.95,
                "top_k": 20,
            },
        )
    )

    body = backend._build_body(
        "q",
        system=None,
        model=None,
        options={"seed": 7},
        think=False,
        format="json",
    )

    assert body["model"] == "/models/qwen3.8"
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert "enable_thinking" not in body
    assert "response_format" not in body
    assert body["max_tokens"] == 8192
    assert body["top_p"] == 0.95
    assert body["top_k"] == 20
    assert body["seed"] == 7
    assert "repetition_penalty" not in body


def test_sync_json_is_buffered_and_canonicalized() -> None:
    def fake_urlopen(request, timeout=None):
        return _sse_response(
            [
                {
                    "choices": [
                        {
                            "delta": {"content": '```json\n{"ok":true}\n```'},
                            "finish_reason": "stop",
                        },
                    ],
                },
                "[DONE]",
            ],
        )

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        events = list(
            MlxDsparkBackend(
                BackendConfig(base_url="http://test-dspark:11439")
            ).stream_ask(
                "q",
                format="json",
            ),
        )

    assert events[0] == {"response": '{"ok":true}', "done": False}
    assert events[-1]["done_reason"] == "stop"


@pytest.mark.parametrize(
    ("content", "finish_reason", "error"),
    [
        ('{"ok":true,"ok":false}', "stop", "neither a strict object"),
        ('{"ok":true}', "length", "did not finish naturally"),
    ],
)
def test_sync_json_rejects_invalid_or_truncated_output(
    content: str,
    finish_reason: str,
    error: str,
) -> None:
    def fake_urlopen(request, timeout=None):
        return _sse_response(
            [
                {
                    "choices": [
                        {
                            "delta": {"content": content},
                            "finish_reason": finish_reason,
                        },
                    ],
                },
                "[DONE]",
            ],
        )

    with (
        patch("urllib.request.urlopen", side_effect=fake_urlopen),
        pytest.raises(LLMError, match=error),
    ):
        list(
            MlxDsparkBackend(
                BackendConfig(base_url="http://test-dspark:11439")
            ).stream_ask(
                "q",
                format="json",
            ),
        )


def test_sync_json_rejects_missing_done_event() -> None:
    def fake_urlopen(request, timeout=None):
        return _sse_response(
            [
                {
                    "choices": [
                        {
                            "delta": {"content": '{"ok":true}'},
                            "finish_reason": None,
                        },
                    ],
                },
            ],
        )

    with (
        patch("urllib.request.urlopen", side_effect=fake_urlopen),
        pytest.raises(LLMError, match="without a done event"),
    ):
        list(
            MlxDsparkBackend(
                BackendConfig(base_url="http://test-dspark:11439")
            ).stream_ask(
                "q",
                format="json",
            ),
        )


class _AsyncResponse:
    async def __aenter__(self):
        async def lines():
            yield "data: " + json.dumps(
                {
                    "choices": [
                        {
                            "delta": {"content": '{"ok":true}'},
                            "finish_reason": "stop",
                        },
                    ],
                },
            )
            yield "data: [DONE]"

        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.aiter_lines = lines
        return response

    async def __aexit__(self, *args):
        return False


class _AsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def stream(self, method, url, json=None, headers=None):
        return _AsyncResponse()


@pytest.mark.asyncio
async def test_async_json_is_buffered_and_canonicalized() -> None:
    fake_httpx = MagicMock()
    fake_httpx.AsyncClient = _AsyncClient
    fake_httpx.Timeout = lambda value: value

    with patch.dict("sys.modules", {"httpx": fake_httpx}):
        events = []
        async for event in MlxDsparkBackend(
            BackendConfig(base_url="http://test-dspark:11439"),
        ).astream_ask("q", format="json"):
            events.append(event)

    assert events[0] == {"response": '{"ok":true}', "done": False}
    assert events[-1]["done_reason"] == "stop"
