"""local_llm async transport and backend factory tests."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from local_llm import (
    BackendConfig,
    LlamaServerBackend,
    LLMError,
    MlxBackend,
    MlxDsparkBackend,
    MlxLmBackend,
    OllamaBackend,
    backend_from_env,
)

_OLLAMA_CFG = BackendConfig(base_url="http://test-ollama:11434")
_LLAMA_CFG = BackendConfig(base_url="http://test-llama:11435")


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    """各テストでbackend factory用の環境変数を初期化する。"""
    for key in [
        "QWEN_BACKEND",
        "QWEN_OLLAMA_BASE_URL",
        "QWEN_LLAMA_SERVER_BASE_URL",
        "QWEN_MLX_BASE_URL",
        "QWEN_MLX_LM_BASE_URL",
        "QWEN_MLX_DSPARK_BASE_URL",
        "QWEN_MODEL",
        "QWEN_TIMEOUT_SEC",
    ]:
        monkeypatch.delenv(key, raising=False)


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
            "data: "
            + json.dumps(
                {"choices": [{"delta": {"content": "Hi"}, "finish_reason": None}]},
            ),
            "",
            "data: "
            + json.dumps(
                {"choices": [{"delta": {"content": "!"}, "finish_reason": "stop"}]},
            ),
            "",
            "data: "
            + json.dumps(
                {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 2}},
            ),
            "",
            "data: [DONE]",
        ]

        with patch.dict("sys.modules", _patch_httpx()):
            events = []
            async for event in LlamaServerBackend(_LLAMA_CFG).astream_ask("q"):
                events.append(event)

        assert (
            _FakeAsyncClient.captured["url"]
            == "http://test-llama:11435/v1/chat/completions"
        )
        assert (
            _FakeAsyncClient.captured["json"]["chat_template_kwargs"]["enable_thinking"]
            is False
        )
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

        assert (
            _FakeAsyncClient.captured["url"] == "http://test-ollama:11434/api/generate"
        )
        assert _FakeAsyncClient.captured["json"]["think"] is False
        assert events[0]["response"] == "Hi"
        assert events[-1]["done"] is True

    @pytest.mark.asyncio
    async def test_llama_server_astream_chat(self):
        """astream_chat も messages をそのまま OpenAI body に載せる。"""
        _FakeAsyncClient.captured = {}
        _FakeAsyncClient.response_lines = [
            "data: "
            + json.dumps(
                {"choices": [{"delta": {"content": "Yes"}, "finish_reason": "stop"}]},
            ),
            "",
            "data: "
            + json.dumps(
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

    def test_mlx_via_env(self, monkeypatch):
        monkeypatch.setenv("QWEN_BACKEND", "mlx")
        monkeypatch.setenv("QWEN_MLX_BASE_URL", "http://custom-mlx:11437")
        monkeypatch.setenv("QWEN_MODEL", "/models/qwen")

        backend = backend_from_env()

        assert isinstance(backend, MlxBackend)
        assert backend.config.base_url == "http://custom-mlx:11437"
        assert backend.config.model == "/models/qwen"

    def test_mlx_lm_via_env(self, monkeypatch):
        monkeypatch.setenv("QWEN_BACKEND", "mlx_lm")
        monkeypatch.setenv("QWEN_MLX_LM_BASE_URL", "http://custom-mlx-lm:11440")
        monkeypatch.setenv("QWEN_MODEL", "/models/ornith")

        backend = backend_from_env()

        assert isinstance(backend, MlxLmBackend)
        assert backend.config.base_url == "http://custom-mlx-lm:11440"
        assert backend.config.model == "/models/ornith"

    def test_mlx_dspark_via_env(self, monkeypatch):
        monkeypatch.setenv("QWEN_BACKEND", "mlx_dspark")
        monkeypatch.setenv("QWEN_MLX_DSPARK_BASE_URL", "http://custom-dspark:11439")
        monkeypatch.setenv("QWEN_MODEL", "/models/qwen3.8")

        backend = backend_from_env()

        assert isinstance(backend, MlxDsparkBackend)
        assert backend.config.base_url == "http://custom-dspark:11439"
        assert backend.config.model == "/models/qwen3.8"

    def test_unknown_backend_raises(self, monkeypatch):
        monkeypatch.setenv("QWEN_BACKEND", "vllm")
        with pytest.raises(LLMError, match="unknown QWEN_BACKEND"):
            backend_from_env()
