"""Ollama 経由で embedding を取得する（bge-m3, 1024 次元）。

Ollama の `/api/embed` を urllib で叩くシンプルな実装。バッチサイズは呼び出し側で制御。
詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §5.3。
"""
from __future__ import annotations

import json
import struct
import urllib.error
import urllib.request

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
    body = json.dumps({
        "model": model,
        "input": texts,
        "options": {"num_gpu": NOVEL_DB_EMBED_NUM_GPU},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{NOVEL_DB_OLLAMA_BASE_URL}/api/embed",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise EmbeddingError(f"Ollama embed API request failed: {e}") from e
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


def serialize_f32(vec: list[float]) -> bytes:
    """sqlite-vec の vec0 列に格納するバイナリ表現に変換する。"""
    return struct.pack(f"{len(vec)}f", *vec)
