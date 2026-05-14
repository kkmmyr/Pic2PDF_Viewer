"""Ollama 経由で embedding を取得する（bge-m3, 1024 次元）。

Ollama の `/api/embed` を httpx で叩くシンプルな実装。バッチサイズは呼び出し側で制御。
詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §5.3。
"""
from __future__ import annotations

import httpx

from config import (
    NOVEL_DB_EMBED_DIM,
    NOVEL_DB_EMBED_MODEL,
    NOVEL_DB_EMBED_NUM_GPU,
    NOVEL_DB_OLLAMA_BASE_URL,
)

_EMBED_TIMEOUT_SEC = 180


class EmbeddingError(RuntimeError):
    """Ollama embed API 呼び出し失敗時に投げる。"""


def embed_batch(
    texts: list[str],
    *,
    model: str = NOVEL_DB_EMBED_MODEL,
    timeout: int = _EMBED_TIMEOUT_SEC,
) -> list[list[float]]:
    """テキストのリストを embedding に変換する。

    入力が空リストの場合は空リストを返す（API は呼ばない）。
    """
    if not texts:
        return []
    try:
        response = httpx.post(
            f"{NOVEL_DB_OLLAMA_BASE_URL}/api/embed",
            json={
                "model": model,
                "input": texts,
                "options": {"num_gpu": NOVEL_DB_EMBED_NUM_GPU},
            },
            timeout=timeout,
        )
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise EmbeddingError(f"Ollama embed API request failed: {e}") from e
    data = response.json()
    embeddings = data.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != len(texts):
        raise EmbeddingError(
            f"Unexpected response from Ollama embed API "
            f"(expected {len(texts)} embeddings, got {type(embeddings).__name__})"
        )
    for vec in embeddings:
        if len(vec) != NOVEL_DB_EMBED_DIM:
            raise EmbeddingError(
                f"Embedding dimension mismatch (expected {NOVEL_DB_EMBED_DIM}, got {len(vec)}). "
                f"Check NOVEL_DB_EMBED_MODEL ({model}) and NOVEL_DB_EMBED_DIM."
            )
    return embeddings
