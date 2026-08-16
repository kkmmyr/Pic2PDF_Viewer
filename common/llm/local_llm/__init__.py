"""local_llm — Ollama / llama-server を叩く LLM Backend 抽象。

Qwen3.x の thinking モデル特有の地雷（`stream=True` / `think=False` 必須、
`num_predict` を thinking で食い潰される事故）を踏み抜く呼び出しを集約した
共通モジュール。複数プロジェクトから利用される（Pic2PDF / CLI `ask.py` /
MCP サーバー）。

公開 API:

    Backend             — ABC、stream_ask / astream_ask を実装する
    BackendConfig       — 接続設定（base_url, model, timeout, default_options）
    LLMError            — バックエンド呼び出し失敗時に投げる
    OllamaBackend       — Ollama /api/generate
    LlamaServerBackend  — llama.cpp llama-server /v1/chat/completions
    backend_from_env    — 環境変数から Backend を 1 つ作る（CLI / MCP 用）

利用方法（アプリ側、設定を明示渡し）:

    from local_llm import BackendConfig, LlamaServerBackend
    backend = LlamaServerBackend(BackendConfig(
        base_url="http://127.0.0.1:11435",
        model="qwen3.6-iq4xs",
    ))
    for event in backend.stream_ask("こんにちは"):
        print(event)

利用方法（CLI / MCP、環境変数経由）:

    from local_llm import backend_from_env
    backend = backend_from_env()
"""

from ._backend import Backend, BackendConfig, LLMError
from ._factory import backend_from_env
from ._llama_server import LlamaServerBackend
from ._ollama import OllamaBackend

__all__ = [
    "Backend",
    "BackendConfig",
    "LLMError",
    "OllamaBackend",
    "LlamaServerBackend",
    "backend_from_env",
]
