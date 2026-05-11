"""services/novel_db/query_expander.py の単体テスト。

LLM 呼び出しはモック。`_parse_expansions` の整形ロジックと、空入力 / LLM 失敗時の
フォールバック、元の質問が必ず先頭に含まれることを確認する。
"""
from unittest.mock import patch

from services.novel_db.query_expander import _parse_expansions, expand_query


# ---------------------------------------------------------------------------
# _parse_expansions: LLM の応答テキスト整形
# ---------------------------------------------------------------------------

def test_parse_basic_lines():
    response = "ベルナード 弁護士 法廷\nソレス王子 裁判編\nレティ 連携 推理"
    out = _parse_expansions(response, target_n=3)
    assert out == ["ベルナード 弁護士 法廷", "ソレス王子 裁判編", "レティ 連携 推理"]


def test_parse_strips_numbering_dot():
    response = "1. ベルナード 弁護士\n2. ソレス王子 裁判\n3. レティ 連携"
    out = _parse_expansions(response, target_n=3)
    assert out == ["ベルナード 弁護士", "ソレス王子 裁判", "レティ 連携"]


def test_parse_strips_numbering_japanese():
    response = "1．ベルナード 弁護士\n2：ソレス王子 裁判"
    out = _parse_expansions(response, target_n=2)
    assert "ベルナード 弁護士" in out
    assert "ソレス王子 裁判" in out


def test_parse_strips_bullet():
    response = "- ベルナード 弁護士\n・ソレス王子\n* レティ 連携"
    out = _parse_expansions(response, target_n=3)
    assert out == ["ベルナード 弁護士", "ソレス王子", "レティ 連携"]


def test_parse_strips_label_prefix():
    response = "検索クエリ: ベルナード 弁護士\nクエリ：ソレス王子 裁判"
    out = _parse_expansions(response, target_n=2)
    assert out == ["ベルナード 弁護士", "ソレス王子 裁判"]


def test_parse_strips_quotes():
    response = "「ベルナード 弁護士」\n『ソレス王子 裁判』"
    out = _parse_expansions(response, target_n=2)
    assert out == ["ベルナード 弁護士", "ソレス王子 裁判"]


def test_parse_skips_too_long_lines():
    """60 字超の行（説明文っぽい）はスキップする。"""
    long_line = "あ" * 65
    response = f"ベルナード 弁護士\n{long_line}\nソレス王子 裁判"
    out = _parse_expansions(response, target_n=3)
    assert "ベルナード 弁護士" in out
    assert "ソレス王子 裁判" in out
    assert long_line not in out


def test_parse_limits_to_target_n():
    response = "クエリ1\nクエリ2\nクエリ3\nクエリ4\nクエリ5"
    out = _parse_expansions(response, target_n=3)
    assert len(out) == 3


def test_parse_empty_response():
    assert _parse_expansions("", target_n=3) == []
    assert _parse_expansions("\n\n\n", target_n=3) == []


# ---------------------------------------------------------------------------
# expand_query: 統合動作
# ---------------------------------------------------------------------------

def test_expand_returns_question_only_for_empty_input():
    """空文字の質問は LLM を呼ばずに元の文字列を返す。"""
    with patch("urllib.request.urlopen") as mock_urlopen:
        assert expand_query("") == [""]
        assert expand_query("   ") == ["   "]
    mock_urlopen.assert_not_called()


def test_expand_returns_question_only_when_n_is_one():
    """n=1 のときは LLM を呼ばず元の質問だけ返す。"""
    with patch("urllib.request.urlopen") as mock_urlopen:
        out = expand_query("質問", n=1)
    assert out == ["質問"]
    mock_urlopen.assert_not_called()


def test_expand_question_is_always_first():
    """元の質問は必ず結果の先頭に来る。"""
    fake_response = _make_ollama_stream([
        "ベルナード 弁護士\nソレス王子 裁判\nレティ 連携",
    ])
    with patch("urllib.request.urlopen", return_value=fake_response):
        out = expand_query("ベルナードの裁判での役割は？", n=4)
    assert out[0] == "ベルナードの裁判での役割は？"
    assert len(out) == 4


def test_expand_dedupes_against_question():
    """LLM が元の質問とまったく同じクエリを生成しても重複は除く。"""
    fake_response = _make_ollama_stream([
        "質問\n別のクエリ\nさらに別\n4 個目",
    ])
    with patch("urllib.request.urlopen", return_value=fake_response):
        out = expand_query("質問", n=4)
    assert out.count("質問") == 1
    assert "別のクエリ" in out
    assert len(out) <= 4


def test_expand_handles_llm_error_gracefully():
    """LLM 接続エラー時は元の質問のみのリストを返す（後方互換フォールバック）。"""
    import urllib.error

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")
        out = expand_query("質問", n=4)
    assert out == ["質問"]


def test_expand_caps_to_n():
    """LLM がたくさん展開しても結果は n 件に制限される。"""
    fake_response = _make_ollama_stream([
        "q1\nq2\nq3\nq4\nq5\nq6\nq7\nq8",
    ])
    with patch("urllib.request.urlopen", return_value=fake_response):
        out = expand_query("元", n=3)
    assert len(out) == 3
    assert out[0] == "元"


# ---------------------------------------------------------------------------
# テスト用ヘルパー
# ---------------------------------------------------------------------------

class _FakeStreamResponse:
    """urllib.request.urlopen の戻り値をモックするためのコンテキストマネージャ。"""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = lines

    def __iter__(self):
        return iter(self._lines)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def _make_ollama_stream(text_chunks: list[str]) -> _FakeStreamResponse:
    """Ollama NDJSON ストリーム形式のレスポンスを組み立てる。"""
    import json
    lines: list[bytes] = []
    for chunk in text_chunks:
        lines.append((json.dumps({"response": chunk}) + "\n").encode("utf-8"))
    lines.append((json.dumps({"done": True, "done_reason": "stop"}) + "\n").encode("utf-8"))
    return _FakeStreamResponse(lines)
