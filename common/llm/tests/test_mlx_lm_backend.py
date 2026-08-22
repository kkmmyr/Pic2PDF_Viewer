"""`mlx_lm.server`用Backendと限定JSON adapterの回帰テスト。"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from local_llm import BackendConfig, LLMError, MlxLmBackend
from local_llm._json_output import normalize_json_events, normalize_json_object

_CONFIG = BackendConfig(base_url="http://test-mlx-lm:11440")


def _openai_sse_response(chunks: list[dict[str, Any] | str]) -> MagicMock:
    lines: list[bytes] = []
    for chunk in chunks:
        payload = chunk if isinstance(chunk, str) else json.dumps(chunk)
        lines.append(f"data: {payload}\n".encode())
        lines.append(b"\n")
    response = MagicMock()
    response.__iter__ = lambda self: iter(lines)
    response.__enter__ = lambda self: response
    response.__exit__ = lambda self, *args: None
    return response


class TestNormalizeJsonObject:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ('  {"name": "仁耀", "ok": true}\n', '{"name":"仁耀","ok":true}'),
            (
                ' \n```json\n{\n  "name": "珀陽",\n  "ok": true\n}\n```\n ',
                '{"name":"珀陽","ok":true}',
            ),
        ],
    )
    def test_accepts_only_raw_object_or_isolated_json_fence(
        self,
        raw: str,
        expected: str,
    ) -> None:
        assert normalize_json_object(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            '説明です\n```json\n{"ok":true}\n```',
            '```json\n{"ok":true}\n```\n```json\n{"ok":true}\n```',
            '```JSON\n{"ok":true}\n```',
            '```\n{"ok":true}\n```',
            '[{"ok":true}]',
            '"value"',
            '{"ok":true,"ok":false}',
            '{"nested":{"x":1,"x":2}}',
            '{"value":NaN}',
            '{"value":Infinity}',
            '{"ok":',
        ],
    )
    def test_rejects_ambiguous_or_non_strict_output(self, raw: str) -> None:
        with pytest.raises(LLMError):
            normalize_json_object(raw)

    def test_rejects_oversized_output(self) -> None:
        with pytest.raises(LLMError, match="exceeds"):
            normalize_json_object('{"ok":true}', max_chars=4)


class TestNormalizeJsonEvents:
    def test_rejects_non_stop_before_exposing_content(self) -> None:
        events = [
            {"response": '{"ok":true}', "done": False},
            {"response": "", "done": True, "done_reason": "length"},
        ]
        with pytest.raises(LLMError, match="did not finish naturally"):
            list(normalize_json_events(events))

    def test_rejects_missing_done(self) -> None:
        events = [{"response": '{"ok":true}', "done": False}]
        with pytest.raises(LLMError, match="without a done event"):
            list(normalize_json_events(events))

    def test_rejects_data_after_done(self) -> None:
        events = [
            {"response": '{"ok":true}', "done": False},
            {"response": "", "done": True, "done_reason": "stop"},
            {"response": "trailing", "done": False},
        ]
        with pytest.raises(LLMError, match="after the done event"):
            list(normalize_json_events(events))


class TestMlxLmBackendBody:
    def test_uses_nested_thinking_and_omits_unsupported_response_format(self) -> None:
        body = MlxLmBackend(_CONFIG)._build_body(
            "q",
            system=None,
            model="/models/ornith",
            options={
                "top_p": 0.95,
                "top_k": 20,
                "seed": 42,
                "repeat_penalty": 1.15,
            },
            think=True,
            format="json",
        )

        assert body["model"] == "/models/ornith"
        assert body["chat_template_kwargs"] == {"enable_thinking": True}
        assert "enable_thinking" not in body
        assert "response_format" not in body
        assert body["top_p"] == 0.95
        assert body["top_k"] == 20
        assert body["seed"] == 42
        assert body["repetition_penalty"] == 1.15


class TestMlxLmBackendSync:
    def test_json_fence_is_buffered_and_canonicalized(self) -> None:
        captured: dict[str, Any] = {}

        def fake_urlopen(request, timeout=None):
            captured["body"] = json.loads(request.data)
            return _openai_sse_response(
                [
                    {
                        "choices": [
                            {
                                "delta": {"content": '```json\n{"ok":'},
                                "finish_reason": None,
                            },
                        ],
                    },
                    {
                        "choices": [
                            {
                                "delta": {"content": "true}\n```"},
                                "finish_reason": "stop",
                            },
                        ],
                    },
                    {
                        "choices": [],
                        "usage": {"prompt_tokens": 5, "completion_tokens": 7},
                    },
                    "[DONE]",
                ],
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            events = list(
                MlxLmBackend(_CONFIG).stream_ask(
                    "q",
                    think=True,
                    format="json",
                ),
            )

        assert "response_format" not in captured["body"]
        assert captured["body"]["chat_template_kwargs"] == {
            "enable_thinking": True,
        }
        assert events == [
            {"response": '{"ok":true}', "done": False},
            {
                "response": "",
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 5,
                "eval_count": 7,
            },
        ]

    def test_length_finish_is_rejected_even_when_usage_follows(self) -> None:
        def fake_urlopen(request, timeout=None):
            return _openai_sse_response(
                [
                    {
                        "choices": [
                            {
                                "delta": {"content": '{"ok":true}'},
                                "finish_reason": "length",
                            },
                        ],
                    },
                    {
                        "choices": [],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 2},
                    },
                    "[DONE]",
                ],
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises(LLMError, match="did not finish naturally"):
                list(MlxLmBackend(_CONFIG).stream_ask("q", format="json"))

    def test_non_json_stream_remains_incremental(self) -> None:
        def fake_urlopen(request, timeout=None):
            return _openai_sse_response(
                [
                    {
                        "choices": [
                            {"delta": {"content": "Hi"}, "finish_reason": "stop"},
                        ],
                    },
                    {
                        "choices": [],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                    },
                ],
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            events = list(MlxLmBackend(_CONFIG).stream_ask("q"))

        assert events[0]["response"] == "Hi"
        assert events[-1]["done"] is True


class _FakeStreamContext:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    async def __aenter__(self):
        async def aiter_lines():
            for line in self._lines:
                yield line

        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.aiter_lines = aiter_lines
        return response

    async def __aexit__(self, *args):
        return False


class _FakeAsyncClient:
    response_lines: list[str] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def stream(self, method, url, json=None, headers=None):
        return _FakeStreamContext(self.response_lines)


class TestMlxLmBackendAsync:
    @pytest.mark.asyncio
    async def test_async_json_fence_is_canonicalized(self) -> None:
        _FakeAsyncClient.response_lines = [
            "data: "
            + json.dumps(
                {
                    "choices": [
                        {
                            "delta": {"content": '```json\n{"ok":true}\n```'},
                            "finish_reason": "stop",
                        },
                    ],
                },
            ),
            "data: "
            + json.dumps(
                {
                    "choices": [],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 3},
                },
            ),
            "data: [DONE]",
        ]
        fake_httpx = MagicMock()
        fake_httpx.AsyncClient = _FakeAsyncClient
        fake_httpx.Timeout = lambda value: value

        with patch.dict("sys.modules", {"httpx": fake_httpx}):
            events = []
            async for event in MlxLmBackend(_CONFIG).astream_ask(
                "q",
                format="json",
            ):
                events.append(event)

        assert events[0] == {"response": '{"ok":true}', "done": False}
        assert events[-1]["done_reason"] == "stop"
        assert events[-1]["eval_count"] == 3
