"""OllamaまたはMLX経由でembeddingを取得する（bge-m3, 1024次元）。

backendごとのHTTP応答を同じ`list[list[float]]`へ正規化する。
バッチサイズは呼び出し側で制御。
詳細は docs/design/詳細設計/機能別/小説RAG_パイプライン設計.md §3。
"""

from __future__ import annotations

import httpx

from config import (
    NOVEL_DB_EMBED_BACKEND,
    NOVEL_DB_EMBED_DIM,
    NOVEL_DB_EMBED_MODEL,
    NOVEL_DB_EMBED_NUM_GPU,
    NOVEL_DB_MLX_BASE_URL,
    NOVEL_DB_OLLAMA_BASE_URL,
)

_EMBED_TIMEOUT_SEC = 180


class EmbeddingError(RuntimeError):
    """Embedding APIの呼び出しまたは応答検証に失敗した場合に投げる。"""


def _post_json(
    url: str,
    *,
    body: dict[str, object],
    timeout: int,
    backend_label: str,
) -> dict[str, object]:
    try:
        response = httpx.post(url, json=body, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as e:
        raise EmbeddingError(f"{backend_label} embed API request failed: {e}") from e
    if not isinstance(data, dict):
        raise EmbeddingError(
            f"Unexpected response from {backend_label} embed API (expected object, got {type(data).__name__})"
        )
    return data


def _validate_dimensions(
    embeddings: list[object],
    *,
    model: str,
) -> list[list[float]]:
    validated: list[list[float]] = []
    for vec in embeddings:
        if not isinstance(vec, list):
            raise EmbeddingError(f"Unexpected embedding value (expected list, got {type(vec).__name__})")
        if len(vec) != NOVEL_DB_EMBED_DIM:
            raise EmbeddingError(
                f"Embedding dimension mismatch (expected {NOVEL_DB_EMBED_DIM}, got {len(vec)}). "
                f"Check NOVEL_DB_EMBED_MODEL ({model}) and NOVEL_DB_EMBED_DIM."
            )
        validated.append(vec)
    return validated


def _embed_ollama(texts: list[str], *, model: str, timeout: int) -> list[list[float]]:
    data = _post_json(
        f"{NOVEL_DB_OLLAMA_BASE_URL}/api/embed",
        body={
            "model": model,
            "input": texts,
            "options": {"num_gpu": NOVEL_DB_EMBED_NUM_GPU},
        },
        timeout=timeout,
        backend_label="Ollama",
    )
    embeddings = data.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != len(texts):
        raise EmbeddingError(
            "Unexpected response from Ollama embed API "
            f"(expected {len(texts)} embeddings, got {type(embeddings).__name__})"
        )
    return _validate_dimensions(embeddings, model=model)


def _embed_mlx(texts: list[str], *, model: str, timeout: int) -> list[list[float]]:
    data = _post_json(
        f"{NOVEL_DB_MLX_BASE_URL}/v1/embeddings",
        body={"model": model, "input": texts},
        timeout=timeout,
        backend_label="MLX",
    )
    items = data.get("data")
    if not isinstance(items, list) or len(items) != len(texts):
        raise EmbeddingError(
            f"Unexpected response from MLX embed API (expected {len(texts)} embeddings, got {type(items).__name__})"
        )

    by_index: dict[int, object] = {}
    for item in items:
        if not isinstance(item, dict):
            raise EmbeddingError("Unexpected response from MLX embed API (data item is not an object)")
        index = item.get("index")
        if isinstance(index, bool) or not isinstance(index, int):
            raise EmbeddingError("Unexpected response from MLX embed API (index is not an integer)")
        if index < 0 or index >= len(texts) or index in by_index:
            raise EmbeddingError(f"Unexpected response from MLX embed API (invalid index {index})")
        by_index[index] = item.get("embedding")

    expected_indices = set(range(len(texts)))
    if set(by_index) != expected_indices:
        raise EmbeddingError("Unexpected response from MLX embed API (embedding index is missing)")
    return _validate_dimensions([by_index[i] for i in range(len(texts))], model=model)


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
    if NOVEL_DB_EMBED_BACKEND == "ollama":
        return _embed_ollama(texts, model=model, timeout=timeout)
    if NOVEL_DB_EMBED_BACKEND == "mlx":
        return _embed_mlx(texts, model=model, timeout=timeout)
    raise EmbeddingError(f"Unknown NOVEL_DB_EMBED_BACKEND: {NOVEL_DB_EMBED_BACKEND} (supported: 'ollama', 'mlx')")
