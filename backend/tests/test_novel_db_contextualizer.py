"""services/novel_db/contextualizer.py の単体テスト。

LLM 呼び出しはモックする。`_clean_response` の整形ロジックと、空入力での
スキップ動作、`make_embedding_input` の組立てを確認する。
"""

from unittest.mock import patch

from services.novel_db.contextualizer import (
    _clean_response,
    generate_chunk_context,
    make_embedding_input,
)

# ---------------------------------------------------------------------------
# _clean_response: LLM 応答の整形
# ---------------------------------------------------------------------------


def test_clean_response_strips_whitespace():
    assert _clean_response("  位置説明テキスト  ") == "位置説明テキスト"


def test_clean_response_removes_known_prefixes():
    assert _clean_response("位置説明: page 50 の対話シーン") == "page 50 の対話シーン"
    assert _clean_response("場面：page 50 の対話シーン") == "page 50 の対話シーン"
    assert _clean_response("出力: page 50 の対話") == "page 50 の対話"


def test_clean_response_takes_only_first_line():
    out = _clean_response("page 50 の対話シーン\n補足: ...")
    assert out == "page 50 の対話シーン"


def test_clean_response_returns_empty_for_empty_input():
    assert _clean_response("") == ""
    assert _clean_response("   \n   ") == ""


# ---------------------------------------------------------------------------
# generate_chunk_context: 早期スキップ
# ---------------------------------------------------------------------------


def test_generate_returns_empty_for_empty_chunk():
    """空チャンクは LLM を呼ばずに空文字を返す。"""
    with patch("services.novel_db._llm_backend.GEMMA_BACKEND.ask") as mock_ask:
        out = generate_chunk_context("book", "summary", "")
    assert out == ""
    mock_ask.assert_not_called()


def test_generate_returns_empty_when_summary_missing():
    """書籍サマリ未生成のときは LLM を呼ばずに空文字を返す。"""
    with patch("services.novel_db._llm_backend.GEMMA_BACKEND.ask") as mock_ask:
        out = generate_chunk_context("book", "", "本文があるよ")
    assert out == ""
    mock_ask.assert_not_called()


def test_generate_handles_llm_error_gracefully():
    """LLM 接続エラー時 (LLMError) は空文字を返す（例外を伝播させない）。"""
    from local_llm import LLMError

    with patch("services.novel_db._llm_backend.GEMMA_BACKEND.ask") as mock_ask:
        mock_ask.side_effect = LLMError("Ollama request failed: connection refused")
        out = generate_chunk_context("book", "summary", "本文")
    assert out == ""


def test_generate_calls_backend_with_prompt_and_options():
    """_BACKEND.ask に書籍名・サマリ・チャンクを含むプロンプトと適切な options が渡る。"""
    with patch("services.novel_db._llm_backend.GEMMA_BACKEND.ask") as mock_ask:
        mock_ask.return_value = "page 50 の対話シーン"
        out = generate_chunk_context("テスト書籍", "サマリ本文", "チャンク本文")

    assert out == "page 50 の対話シーン"
    assert mock_ask.call_count == 1
    prompt = mock_ask.call_args.args[0]
    assert "テスト書籍" in prompt
    assert "サマリ本文" in prompt
    assert "チャンク本文" in prompt
    # 短答型なので num_predict は控えめ
    assert mock_ask.call_args.kwargs["options"]["num_predict"] == 256


# ---------------------------------------------------------------------------
# make_embedding_input: embedding 入力の組立て
# ---------------------------------------------------------------------------


def test_make_embedding_input_concatenates_when_context_present():
    out = make_embedding_input("page 50 の対話", "デュークが言った『～』")
    assert out.startswith("page 50 の対話")
    assert "デュークが言った" in out
    # 区切りで改行 2 つが入っている
    assert "\n\n" in out


def test_make_embedding_input_falls_back_to_text_only_for_empty_context():
    out = make_embedding_input(None, "本文のみ")
    assert out == "本文のみ"
    out = make_embedding_input("", "本文のみ")
    assert out == "本文のみ"
    out = make_embedding_input("   ", "本文のみ")
    assert out == "本文のみ"
