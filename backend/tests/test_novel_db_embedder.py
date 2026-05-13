"""embedder.py のユニットテスト。Ollama への HTTP 呼び出しをモックする。"""
import json
from unittest.mock import MagicMock, patch

import pytest

from services.novel_db.embedder import EmbeddingError, embed_batch


def _make_response(embeddings: list[list[float]]) -> MagicMock:
    resp = MagicMock()
    resp.read.return_value = json.dumps({"embeddings": embeddings}).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


@patch("services.novel_db.embedder.urllib.request.urlopen")
def test_embed_batch_sends_num_gpu_option(mock_urlopen):
    """POST ボディに options.num_gpu が含まれることを確認する。"""
    dim = 1024
    mock_urlopen.return_value = _make_response([[0.0] * dim])

    embed_batch(["hello"])

    call_args = mock_urlopen.call_args
    req = call_args[0][0]
    body = json.loads(req.data.decode())
    assert "options" in body
    assert "num_gpu" in body["options"]


@patch("services.novel_db.embedder.urllib.request.urlopen")
def test_embed_batch_empty_returns_empty(mock_urlopen):
    """空リストは API を叩かずに空リストを返す。"""
    result = embed_batch([])
    mock_urlopen.assert_not_called()
    assert result == []


@patch("services.novel_db.embedder.urllib.request.urlopen")
def test_embed_batch_dimension_mismatch_raises(mock_urlopen):
    """次元が NOVEL_DB_EMBED_DIM と異なれば EmbeddingError を投げる。"""
    mock_urlopen.return_value = _make_response([[0.0] * 512])  # 1024 ではない

    with pytest.raises(EmbeddingError, match="dimension mismatch"):
        embed_batch(["hello"])
