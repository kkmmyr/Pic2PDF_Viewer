"""embedder.py のユニットテスト。Ollama への HTTP 呼び出しをモックする。"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from services.novel_db.embedder import EmbeddingError, embed_batch


def _make_response(embeddings: list[list[float]]) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"embeddings": embeddings}
    resp.raise_for_status.return_value = None
    return resp


@patch("services.novel_db.embedder.httpx.post")
def test_embed_batch_sends_num_gpu_option(mock_post):
    """POST ボディに options.num_gpu が含まれることを確認する。"""
    dim = 1024
    mock_post.return_value = _make_response([[0.0] * dim])

    embed_batch(["hello"])

    call_kwargs = mock_post.call_args.kwargs
    body = call_kwargs["json"]
    assert "options" in body
    assert "num_gpu" in body["options"]


@patch("services.novel_db.embedder.httpx.post")
def test_embed_batch_empty_returns_empty(mock_post):
    """空リストは API を叩かずに空リストを返す。"""
    result = embed_batch([])
    mock_post.assert_not_called()
    assert result == []


@patch("services.novel_db.embedder.httpx.post")
def test_embed_batch_dimension_mismatch_raises(mock_post):
    """次元が NOVEL_DB_EMBED_DIM と異なれば EmbeddingError を投げる。"""
    mock_post.return_value = _make_response([[0.0] * 512])  # 1024 ではない

    with pytest.raises(EmbeddingError, match="dimension mismatch"):
        embed_batch(["hello"])


@patch("services.novel_db.embedder.httpx.post")
def test_embed_batch_http_error_raises_embedding_error(mock_post):
    """httpx.HTTPError は EmbeddingError に変換される。"""
    mock_post.side_effect = httpx.RequestError("connection failed")

    with pytest.raises(EmbeddingError, match="request failed"):
        embed_batch(["hello"])
