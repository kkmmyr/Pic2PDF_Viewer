"""local_llm パッケージのユニットテスト。

A-6 で旧 test_qwen_client.py から移行。テスト対象を BackendConfig dataclass
+ Backend ABC + 2 つの具象 Backend + SSE 純関数 + backend_from_env に分割した。

実 HTTP は urllib (sync) / httpx (async) を mock してリクエストボディと URL を
検証する。
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from local_llm import (
    Backend,
    BackendConfig,
    LlamaServerBackend,
    LLMError,
    OllamaBackend,
    backend_from_env,
)
from local_llm._sse import convert_openai_chunk, fallback_done_event

# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    """各テストで QWEN_* 環境変数を初期化する（backend_from_env 用）。"""
    for key in [
        "QWEN_BACKEND",
        "QWEN_OLLAMA_BASE_URL",
        "QWEN_LLAMA_SERVER_BASE_URL",
        "QWEN_MODEL",
        "QWEN_TIMEOUT_SEC",
    ]:
        monkeypatch.delenv(key, raising=False)


def _ollama_ndjson_response(chunks: list[dict]) -> MagicMock:
    """urlopen の context manager が返す NDJSON レスポンスを模倣する。"""
    lines = [json.dumps(c).encode("utf-8") + b"\n" for c in chunks]
    resp = MagicMock()
    resp.__iter__ = lambda self: iter(lines)
    resp.__enter__ = lambda self: resp
    resp.__exit__ = lambda self, *args: None
    return resp


def _openai_sse_response(chunks: list[dict | str]) -> MagicMock:
    """llama-server の OpenAI SSE 形式レスポンスを模倣する。

    chunks に str を渡した場合は生 SSE 行（"[DONE]" 等）として扱う。
    """
    lines: list[bytes] = []
    for c in chunks:
        if isinstance(c, str):
            lines.append(f"data: {c}\n".encode())
        else:
            lines.append(f"data: {json.dumps(c)}\n".encode())
        lines.append(b"\n")
    resp = MagicMock()
    resp.__iter__ = lambda self: iter(lines)
    resp.__enter__ = lambda self: resp
    resp.__exit__ = lambda self, *args: None
    return resp


_OLLAMA_CFG = BackendConfig(base_url="http://test-ollama:11434")
_LLAMA_CFG = BackendConfig(base_url="http://test-llama:11435")


# ---------------------------------------------------------------------------
# BackendConfig
# ---------------------------------------------------------------------------

class TestBackendConfig:
    def test_defaults(self):
        cfg = BackendConfig(base_url="http://x")
        assert cfg.model == "qwen3.6:35b-a3b"
        assert cfg.timeout == 600
        assert cfg.default_options["temperature"] == 0.2
        assert cfg.default_options["num_predict"] == 8192
        assert cfg.default_options["num_ctx"] == 8192

    def test_frozen(self):
        cfg = BackendConfig(base_url="http://x")
        with pytest.raises(Exception):  # noqa: B017  (FrozenInstanceError or AttributeError)
            cfg.base_url = "http://y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Backend ABC
# ---------------------------------------------------------------------------

class TestBackendABC:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            Backend(BackendConfig(base_url="x"))

    def test_concrete_backends_are_instantiable(self):
        # 実体テストは後段の TestOllamaBackend / TestLlamaServerBackend で
        assert isinstance(OllamaBackend(_OLLAMA_CFG), Backend)
        assert isinstance(LlamaServerBackend(_LLAMA_CFG), Backend)


# ---------------------------------------------------------------------------
# SSE 純関数
# ---------------------------------------------------------------------------

class TestConvertOpenAIChunk:
    def test_normal_token_delta(self):
        chunk = {"choices": [{"delta": {"content": "Hello"}, "finish_reason": None}]}
        assert convert_openai_chunk(chunk) == {"response": "Hello", "done": False}

    def test_empty_delta_returns_none(self):
        # role: assistant のみのデルタは skip
        chunk = {"choices": [{"delta": {"role": "assistant"}, "finish_reason": None}]}
        assert convert_openai_chunk(chunk) is None

    def test_finish_reason_chunk_uses_pending_marker(self):
        chunk = {"choices": [{"delta": {"content": "!"}, "finish_reason": "stop"}]}
        event = convert_openai_chunk(chunk)
        assert event["done"] is False
        assert event["_finish"] == "stop"
        assert event["response"] == "!"

    def test_usage_only_chunk_marks_done(self):
        chunk = {
            "choices": [],
            "usage": {"prompt_tokens": 5, "completion_tokens": 7},
        }
        event = convert_openai_chunk(chunk)
        assert event["done"] is True
        assert event["prompt_eval_count"] == 5
        assert event["eval_count"] == 7

    def test_empty_choices_no_usage_returns_none(self):
        # choices=[] かつ usage 無し → どちらでもない（None）
        assert convert_openai_chunk({"choices": []}) is None


class TestFallbackDoneEvent:
    def test_returns_done_with_none_counts(self):
        ev = fallback_done_event("stop")
        assert ev["done"] is True
        assert ev["done_reason"] == "stop"
        assert ev["prompt_eval_count"] is None
        assert ev["eval_count"] is None


# ---------------------------------------------------------------------------
# OllamaBackend
# ---------------------------------------------------------------------------

class TestOllamaBackendBody:
    def test_default_think_false(self):
        body = OllamaBackend(_OLLAMA_CFG)._build_body(
            "hello", system=None, model=None, options=None, think=None, context=None,
        )
        assert body["think"] is False
        assert body["stream"] is True
        assert body["prompt"] == "hello"
        assert body["model"] == "qwen3.6:35b-a3b"  # config default

    def test_explicit_think_true(self):
        body = OllamaBackend(_OLLAMA_CFG)._build_body(
            "hello", system=None, model=None, options=None, think=True, context=None,
        )
        assert body["think"] is True

    def test_options_merge_overrides_defaults(self):
        body = OllamaBackend(_OLLAMA_CFG)._build_body(
            "x", system=None, model=None,
            options={"temperature": 0.9, "num_ctx": 32768},
            think=None, context=None,
        )
        assert body["options"]["temperature"] == 0.9
        assert body["options"]["num_ctx"] == 32768
        # 未指定のデフォルトは保持される
        assert body["options"]["num_predict"] == 8192

    def test_system_and_context_optional(self):
        body = OllamaBackend(_OLLAMA_CFG)._build_body(
            "x", system="sys", model=None, options=None, think=None,
            context=[1, 2, 3],
        )
        assert body["system"] == "sys"
        assert body["context"] == [1, 2, 3]

    def test_explicit_model_overrides_config(self):
        body = OllamaBackend(_OLLAMA_CFG)._build_body(
            "x", system=None, model="custom-model", options=None, think=None, context=None,
        )
        assert body["model"] == "custom-model"

    def test_format_json_sets_top_level_key(self):
        body = OllamaBackend(_OLLAMA_CFG)._build_body(
            "x", system=None, model=None, options=None, think=None, context=None,
            format="json",
        )
        # Ollama API 仕様: format は body トップレベル (options の中ではない)
        assert body["format"] == "json"
        assert "format" not in body["options"]

    def test_format_none_omits_key(self):
        body = OllamaBackend(_OLLAMA_CFG)._build_body(
            "x", system=None, model=None, options=None, think=None, context=None,
        )
        assert "format" not in body


class TestOllamaBackendStreamAsk:
    def test_dispatches_to_correct_endpoint(self):
        captured: dict[str, Any] = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data)
            return _ollama_ndjson_response([
                {"response": "Hi", "done": False},
                {"response": "", "done": True, "eval_count": 1},
            ])

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            events = list(OllamaBackend(_OLLAMA_CFG).stream_ask("hello"))

        assert captured["url"] == "http://test-ollama:11434/api/generate"
        assert captured["body"]["think"] is False
        assert captured["body"]["prompt"] == "hello"
        assert events[0]["response"] == "Hi"
        assert events[-1]["done"] is True

    def test_url_error_wrapped_in_llm_error(self):
        import urllib.error

        def fake_urlopen(req, timeout=None):
            raise urllib.error.URLError("connection refused")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises(LLMError, match="Ollama request failed"):
                list(OllamaBackend(_OLLAMA_CFG).stream_ask("x"))


# ---------------------------------------------------------------------------
# LlamaServerBackend
# ---------------------------------------------------------------------------

class TestLlamaServerBackendBody:
    def test_uses_messages_format(self):
        body = LlamaServerBackend(_LLAMA_CFG)._build_body(
            "hello", system=None, model=None, options=None, think=None,
        )
        assert body["messages"] == [{"role": "user", "content": "hello"}]
        assert body["stream"] is True
        assert "prompt" not in body  # OpenAI 形式では prompt キー無し

    def test_system_message_prepended(self):
        body = LlamaServerBackend(_LLAMA_CFG)._build_body(
            "q", system="you are helpful", model=None, options=None, think=None,
        )
        assert body["messages"][0] == {"role": "system", "content": "you are helpful"}
        assert body["messages"][1] == {"role": "user", "content": "q"}

    def test_chat_template_kwargs_enable_thinking_default_false(self):
        body = LlamaServerBackend(_LLAMA_CFG)._build_body(
            "q", system=None, model=None, options=None, think=None,
        )
        assert body["chat_template_kwargs"]["enable_thinking"] is False

    def test_chat_template_kwargs_enable_thinking_explicit_true(self):
        body = LlamaServerBackend(_LLAMA_CFG)._build_body(
            "q", system=None, model=None, options=None, think=True,
        )
        assert body["chat_template_kwargs"]["enable_thinking"] is True

    def test_max_tokens_from_num_predict(self):
        body = LlamaServerBackend(_LLAMA_CFG)._build_body(
            "q", system=None, model=None, options={"num_predict": 1024}, think=None,
        )
        assert body["max_tokens"] == 1024

    def test_top_p_only_if_provided(self):
        body = LlamaServerBackend(_LLAMA_CFG)._build_body(
            "q", system=None, model=None, options=None, think=None,
        )
        assert "top_p" not in body
        body2 = LlamaServerBackend(_LLAMA_CFG)._build_body(
            "q", system=None, model=None, options={"top_p": 0.95}, think=None,
        )
        assert body2["top_p"] == 0.95

    def test_format_json_sets_response_format(self):
        body = LlamaServerBackend(_LLAMA_CFG)._build_body(
            "q", system=None, model=None, options=None, think=None, format="json",
        )
        # OpenAI 互換: response_format={"type": "json_object"}
        assert body["response_format"] == {"type": "json_object"}

    def test_format_none_omits_response_format(self):
        body = LlamaServerBackend(_LLAMA_CFG)._build_body(
            "q", system=None, model=None, options=None, think=None,
        )
        assert "response_format" not in body

    def test_format_unsupported_raises_llm_error(self):
        with pytest.raises(LLMError, match="not supported"):
            LlamaServerBackend(_LLAMA_CFG)._build_body(
                "q", system=None, model=None, options=None, think=None, format="yaml",
            )


class TestLlamaServerBackendStreamAsk:
    def test_dispatches_with_usage_chunk(self):
        """正常系: finish_reason チャンクの後に usage チャンクが届くケース。"""
        captured: dict[str, Any] = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data)
            return _openai_sse_response([
                {"choices": [{"delta": {"role": "assistant"}, "finish_reason": None}]},
                {"choices": [{"delta": {"content": "Hello"}, "finish_reason": None}]},
                {"choices": [{"delta": {"content": " world"}, "finish_reason": "stop"}]},
                {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 2}},
                "[DONE]",
            ])

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            events = list(LlamaServerBackend(_LLAMA_CFG).stream_ask("hi"))

        assert captured["url"] == "http://test-llama:11435/v1/chat/completions"
        assert captured["body"]["chat_template_kwargs"]["enable_thinking"] is False
        assert captured["body"]["messages"] == [{"role": "user", "content": "hi"}]
        assert captured["body"]["stream_options"]["include_usage"] is True
        # 内部マーカー `_finish` は外に漏れない
        assert all("_finish" not in e for e in events)
        response_texts = [e.get("response", "") for e in events]
        assert "Hello" in response_texts
        assert " world" in response_texts
        # done=True は 1 度だけ・eval_count 付き
        done_events = [e for e in events if e.get("done")]
        assert len(done_events) == 1
        assert done_events[0]["done_reason"] == "stop"
        assert done_events[0]["eval_count"] == 2
        assert done_events[0]["prompt_eval_count"] == 5

    def test_fallback_done_when_usage_chunk_missing(self):
        """include_usage=true でも usage チャンクが届かない場合のフォールバック。"""
        def fake_urlopen(req, timeout=None):
            return _openai_sse_response([
                {"choices": [{"delta": {"content": "x"}, "finish_reason": "stop"}]},
                "[DONE]",
            ])

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            events = list(LlamaServerBackend(_LLAMA_CFG).stream_ask("hi"))

        done_events = [e for e in events if e.get("done")]
        assert len(done_events) == 1
        assert done_events[0]["done_reason"] == "stop"
        assert done_events[0]["eval_count"] is None

    def test_context_resume_raises(self):
        with pytest.raises(LLMError, match="context resume"):
            list(LlamaServerBackend(_LLAMA_CFG).stream_ask("x", context=[1, 2, 3]))

    def test_stream_chat_sends_messages_as_is(self):
        """stream_chat は messages をそのまま OpenAI body に載せる（multi-turn）。"""
        captured: dict[str, Any] = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data)
            return _openai_sse_response([
                {"choices": [{"delta": {"content": "OK"}, "finish_reason": "stop"}]},
                {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 1}},
                "[DONE]",
            ])

        messages = [
            {"role": "system", "content": "あなたはアシスタント"},
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2 を踏まえて..."},
        ]
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            events = list(LlamaServerBackend(_LLAMA_CFG).stream_chat(messages))

        assert captured["body"]["messages"] == messages
        assert captured["body"]["chat_template_kwargs"]["enable_thinking"] is False
        done_events = [e for e in events if e.get("done")]
        assert len(done_events) == 1
        assert done_events[0]["eval_count"] == 1


class TestStreamChatDefaultNotImplemented:
    def test_ollama_chat_raises_not_implemented(self):
        with pytest.raises(NotImplementedError, match="multi-turn chat"):
            list(OllamaBackend(_OLLAMA_CFG).stream_chat([{"role": "user", "content": "x"}]))

    def test_url_error_wrapped_in_llm_error(self):
        import urllib.error

        def fake_urlopen(req, timeout=None):
            raise urllib.error.URLError("connection refused")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises(LLMError, match="llama-server request failed"):
                list(LlamaServerBackend(_LLAMA_CFG).stream_ask("x"))


# ---------------------------------------------------------------------------
# Backend.ask（同期、集約）
# ---------------------------------------------------------------------------

class TestAskAggregation:
    def test_concatenates_response_tokens(self):
        def fake_urlopen(req, timeout=None):
            return _openai_sse_response([
                {"choices": [{"delta": {"content": "ABC"}, "finish_reason": None}]},
                {"choices": [{"delta": {"content": "DEF"}, "finish_reason": "stop"}]},
                {"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 2}},
                "[DONE]",
            ])

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            text = LlamaServerBackend(_LLAMA_CFG).ask("hi")
        assert text == "ABCDEF"


# ---------------------------------------------------------------------------
# async — httpx をライブラリレベルで mock
# ---------------------------------------------------------------------------

class _FakeStreamCtx:
    """httpx の `client.stream(...)` が返す async context manager を模倣。"""
    def __init__(self, lines: list[str]):
        self._lines = lines

    async def __aenter__(self):
        async def aiter_lines():
            for line in self._lines:
                yield line

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.aiter_lines = aiter_lines
        return resp

    async def __aexit__(self, *args):
        return False


class _FakeAsyncClient:
    """httpx.AsyncClient の最低限のスタブ。"""
    captured: dict[str, Any] = {}
    response_lines: list[str] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def stream(self, method, url, json=None, headers=None):
        _FakeAsyncClient.captured["method"] = method
        _FakeAsyncClient.captured["url"] = url
        _FakeAsyncClient.captured["json"] = json
        return _FakeStreamCtx(_FakeAsyncClient.response_lines)


def _patch_httpx() -> dict:
    """httpx を _FakeAsyncClient で差し替えるパッチを作る。"""
    fake_httpx = MagicMock()
    fake_httpx.AsyncClient = _FakeAsyncClient
    fake_httpx.Timeout = lambda x: x
    return {"httpx": fake_httpx}


class TestAstreamAsk:
    @pytest.mark.asyncio
    async def test_llama_server_async_path(self):
        _FakeAsyncClient.captured = {}
        _FakeAsyncClient.response_lines = [
            "data: " + json.dumps(
                {"choices": [{"delta": {"content": "Hi"}, "finish_reason": None}]},
            ),
            "",
            "data: " + json.dumps(
                {"choices": [{"delta": {"content": "!"}, "finish_reason": "stop"}]},
            ),
            "",
            "data: " + json.dumps(
                {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 2}},
            ),
            "",
            "data: [DONE]",
        ]

        with patch.dict("sys.modules", _patch_httpx()):
            events = []
            async for event in LlamaServerBackend(_LLAMA_CFG).astream_ask("q"):
                events.append(event)

        assert _FakeAsyncClient.captured["url"] == "http://test-llama:11435/v1/chat/completions"
        assert _FakeAsyncClient.captured["json"]["chat_template_kwargs"]["enable_thinking"] is False
        text = "".join(e.get("response", "") for e in events)
        assert text == "Hi!"
        assert events[-1]["done"] is True

    @pytest.mark.asyncio
    async def test_ollama_async_path(self):
        _FakeAsyncClient.captured = {}
        _FakeAsyncClient.response_lines = [
            json.dumps({"response": "Hi", "done": False}),
            json.dumps({"response": "", "done": True, "eval_count": 1}),
        ]

        with patch.dict("sys.modules", _patch_httpx()):
            events = []
            async for event in OllamaBackend(_OLLAMA_CFG).astream_ask("q"):
                events.append(event)

        assert _FakeAsyncClient.captured["url"] == "http://test-ollama:11434/api/generate"
        assert _FakeAsyncClient.captured["json"]["think"] is False
        assert events[0]["response"] == "Hi"
        assert events[-1]["done"] is True

    @pytest.mark.asyncio
    async def test_llama_server_astream_chat(self):
        """astream_chat も messages をそのまま OpenAI body に載せる。"""
        _FakeAsyncClient.captured = {}
        _FakeAsyncClient.response_lines = [
            "data: " + json.dumps(
                {"choices": [{"delta": {"content": "Yes"}, "finish_reason": "stop"}]},
            ),
            "",
            "data: " + json.dumps(
                {"choices": [], "usage": {"prompt_tokens": 4, "completion_tokens": 1}},
            ),
            "",
            "data: [DONE]",
        ]
        messages = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
        ]

        with patch.dict("sys.modules", _patch_httpx()):
            events = []
            async for event in LlamaServerBackend(_LLAMA_CFG).astream_chat(messages):
                events.append(event)

        assert _FakeAsyncClient.captured["json"]["messages"] == messages
        text = "".join(e.get("response", "") for e in events)
        assert text == "Yes"
        assert events[-1]["done"] is True

    @pytest.mark.asyncio
    async def test_llama_server_async_context_raises(self):
        with pytest.raises(LLMError, match="context resume"):
            async for _ in LlamaServerBackend(_LLAMA_CFG).astream_ask("x", context=[1]):
                pass


# ---------------------------------------------------------------------------
# backend_from_env
# ---------------------------------------------------------------------------

class TestBackendFromEnv:
    def test_default_is_llama_server(self):
        backend = backend_from_env()
        assert isinstance(backend, LlamaServerBackend)
        assert backend.config.base_url == "http://127.0.0.1:11435"
        assert backend.config.model == "qwen3.6:35b-a3b"
        assert backend.config.timeout == 600

    def test_ollama_via_env(self, monkeypatch):
        monkeypatch.setenv("QWEN_BACKEND", "ollama")
        monkeypatch.setenv("QWEN_OLLAMA_BASE_URL", "http://custom-ollama:11434")
        monkeypatch.setenv("QWEN_MODEL", "qwen3.6:14b")
        monkeypatch.setenv("QWEN_TIMEOUT_SEC", "300")

        backend = backend_from_env()
        assert isinstance(backend, OllamaBackend)
        assert backend.config.base_url == "http://custom-ollama:11434"
        assert backend.config.model == "qwen3.6:14b"
        assert backend.config.timeout == 300

    def test_unknown_backend_raises(self, monkeypatch):
        monkeypatch.setenv("QWEN_BACKEND", "vllm")
        with pytest.raises(LLMError, match="unknown QWEN_BACKEND"):
            backend_from_env()
