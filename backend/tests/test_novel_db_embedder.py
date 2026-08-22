"""embedder.pyのユニットテスト。Ollama / MLXへのHTTP呼び出しをmockする。"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from services.novel_db.embedder import EmbeddingError, embed_batch


@pytest.fixture(autouse=True)
def default_to_ollama_backend():
    """開発端末の.envに左右されず、既定経路をOllamaとして検証する。"""
    with patch("services.novel_db.embedder.NOVEL_DB_EMBED_BACKEND", "ollama"):
        yield


def _make_response(embeddings: list[list[float]]) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"embeddings": embeddings}
    resp.raise_for_status.return_value = None
    return resp


def _make_mlx_response(items: list[dict]) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"object": "list", "data": items}
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


@patch("services.novel_db.embedder.httpx.post")
def test_embed_batch_mlx_sorts_by_response_index(mock_post):
    dim = 1024
    mock_post.return_value = _make_mlx_response(
        [
            {"index": 1, "embedding": [2.0] * dim},
            {"index": 0, "embedding": [1.0] * dim},
        ]
    )

    with patch("services.novel_db.embedder.NOVEL_DB_EMBED_BACKEND", "mlx"):
        result = embed_batch(["first", "second"], model="/models/bge-m3")

    assert result[0][0] == 1.0
    assert result[1][0] == 2.0
    call_args = mock_post.call_args
    assert call_args.args[0] == "http://127.0.0.1:11437/v1/embeddings"
    assert call_args.kwargs["json"] == {
        "model": "/models/bge-m3",
        "input": ["first", "second"],
    }


@patch("services.novel_db.embedder.httpx.post")
def test_embed_batch_mlx_duplicate_index_raises(mock_post):
    dim = 1024
    mock_post.return_value = _make_mlx_response(
        [
            {"index": 0, "embedding": [1.0] * dim},
            {"index": 0, "embedding": [2.0] * dim},
        ]
    )

    with patch("services.novel_db.embedder.NOVEL_DB_EMBED_BACKEND", "mlx"):
        with pytest.raises(EmbeddingError, match="invalid index 0"):
            embed_batch(["first", "second"])


@patch("services.novel_db.embedder.httpx.post")
def test_embed_batch_mlx_dimension_mismatch_raises(mock_post):
    mock_post.return_value = _make_mlx_response([{"index": 0, "embedding": [0.0] * 512}])

    with patch("services.novel_db.embedder.NOVEL_DB_EMBED_BACKEND", "mlx"):
        with pytest.raises(EmbeddingError, match="dimension mismatch"):
            embed_batch(["hello"])


@patch("services.novel_db.embedder.httpx.post")
def test_embed_batch_unknown_backend_fails_without_http(mock_post):
    with patch("services.novel_db.embedder.NOVEL_DB_EMBED_BACKEND", "unknown"):
        with pytest.raises(EmbeddingError, match="Unknown NOVEL_DB_EMBED_BACKEND"):
            embed_batch(["hello"])
    mock_post.assert_not_called()
