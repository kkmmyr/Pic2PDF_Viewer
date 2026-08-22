"""環境変数から `Backend` を 1 つ作るヘルパー（CLI / MCP 専用）。

Pic2PDF 等のアプリは `config.py` の値から直接 `BackendConfig` を作って
`OllamaBackend` / `LlamaServerBackend` / `MlxBackend` / `MlxLmBackend`を
instantiateするため、こちらは使わない。

環境変数を読むのは本ファイルの 1 箇所のみ。他のモジュール (`Backend` 抽象や
具体実装) は引数渡しで動く設計を維持する。
"""

from __future__ import annotations

import os

from ._backend import Backend, BackendConfig, LLMError
from ._llama_server import LlamaServerBackend
from ._mlx import MlxBackend
from ._mlx_lm import MlxLmBackend
from ._ollama import OllamaBackend


def backend_from_env() -> Backend:
    """`QWEN_BACKEND` 環境変数を見て `Backend` を 1 つ返す。

    | 変数 | 既定 | 用途 |
    |---|---|---|
    | `QWEN_BACKEND` | `llama_server` | `llama_server` / `ollama` / `mlx` / `mlx_lm`を選択 |
    | `QWEN_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama base URL |
    | `QWEN_LLAMA_SERVER_BASE_URL` | `http://127.0.0.1:11435` | llama-server base URL |
    | `QWEN_MLX_BASE_URL` | `http://127.0.0.1:11437` | MLX server base URL |
    | `QWEN_MLX_LM_BASE_URL` | `http://127.0.0.1:11440` | MLX-LM server base URL |
    | `QWEN_MODEL` | `qwen3.6:35b-a3b` | デフォルトモデル |
    | `QWEN_TIMEOUT_SEC` | `600` | リクエスト timeout 秒 |

    変数名に `QWEN_` プレフィックスが残っているのは歴史的経緯
    （ADR-0007 / B-14 で導入）。Phase B で `LLM_*` への改名を検討予定。
    """
    kind = os.environ.get("QWEN_BACKEND", "llama_server")
    model = os.environ.get("QWEN_MODEL", "qwen3.6:35b-a3b")
    timeout = int(os.environ.get("QWEN_TIMEOUT_SEC", "600"))

    if kind == "llama_server":
        return LlamaServerBackend(
            BackendConfig(
                base_url=os.environ.get(
                    "QWEN_LLAMA_SERVER_BASE_URL",
                    "http://127.0.0.1:11435",
                ),
                model=model,
                timeout=timeout,
            )
        )
    if kind == "ollama":
        return OllamaBackend(
            BackendConfig(
                base_url=os.environ.get(
                    "QWEN_OLLAMA_BASE_URL",
                    "http://localhost:11434",
                ),
                model=model,
                timeout=timeout,
            )
        )
    if kind == "mlx":
        return MlxBackend(
            BackendConfig(
                base_url=os.environ.get(
                    "QWEN_MLX_BASE_URL",
                    "http://127.0.0.1:11437",
                ),
                model=model,
                timeout=timeout,
            )
        )
    if kind == "mlx_lm":
        return MlxLmBackend(
            BackendConfig(
                base_url=os.environ.get(
                    "QWEN_MLX_LM_BASE_URL",
                    "http://127.0.0.1:11440",
                ),
                model=model,
                timeout=timeout,
            )
        )
    raise LLMError(f"unknown QWEN_BACKEND: {kind}")
