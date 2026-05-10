"""services/novel_db/character_extractor.py の単体テスト。

Ollama 呼び出しはモックする（テストでは _parse_names と短文スキップだけ確認）。
"""
from unittest.mock import patch

from services.novel_db.character_extractor import _parse_names, extract_main_characters


# ---------------------------------------------------------------------------
# _parse_names
# ---------------------------------------------------------------------------

def test_parse_names_simple_csv():
    assert _parse_names("レティ, デューク, アストリッド") == [
        "レティ", "デューク", "アストリッド"
    ]


def test_parse_names_japanese_comma():
    assert _parse_names("レティ、デューク") == ["レティ", "デューク"]


def test_parse_names_with_prompt_echo():
    """LLM がプロンプトを反復しても、`:` 以降を採用できる。"""
    assert _parse_names("主要登場人物: レティ, デューク") == ["レティ", "デューク"]
    assert _parse_names("主要登場人物（カンマ区切り）: レティ") == ["レティ"]


def test_parse_names_returns_empty_for_unknown():
    assert _parse_names("不明") == []
    assert _parse_names("該当なし") == []
    assert _parse_names("") == []


def test_parse_names_strips_brackets_and_quotes():
    assert _parse_names("「レティ」, 『デューク』") == ["レティ", "デューク"]


def test_parse_names_caps_at_three():
    out = _parse_names("レティ, デューク, アストリッド, グイード, フリート")
    assert len(out) == 3


def test_parse_names_takes_only_first_line():
    """改行が混じった応答でも最初の行のみ採用。"""
    assert _parse_names("レティ, デューク\n説明：…") == ["レティ", "デューク"]


def test_parse_names_skips_overly_long_fragments():
    """説明文が混入した場合に過度に長い断片はスキップされる。"""
    long = "あ" * 50
    out = _parse_names(f"レティ, {long}, デューク")
    assert "レティ" in out
    assert "デューク" in out
    assert long not in out


# ---------------------------------------------------------------------------
# extract_main_characters の境界条件
# ---------------------------------------------------------------------------

def test_extract_returns_empty_for_empty_text():
    assert extract_main_characters("") == []
    assert extract_main_characters("   ") == []


def test_extract_returns_empty_for_too_short_text():
    assert extract_main_characters("短い") == []


def test_extract_calls_ollama_and_parses_response():
    """urlopen をモックして、ストリーミング応答を _parse_names に渡せることを確認。"""
    # 各行が NDJSON。ストリーミング形式（stream=True 想定）。
    stream_lines = [
        '{"response": "レティ"}',
        '{"response": ", "}',
        '{"response": "デューク"}',
        '{"done": true, "done_reason": "stop"}',
    ]

    class FakeStreamResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            return iter(line.encode("utf-8") + b"\n" for line in stream_lines)

    with patch("services.novel_db.character_extractor.urllib.request.urlopen") as urlopen:
        urlopen.return_value = FakeStreamResp()
        result = extract_main_characters("これは十分に長い本文テキストです。" * 5)

    assert result == ["レティ", "デューク"]


def test_extract_returns_empty_on_url_error():
    """Ollama 接続失敗時は例外を伝播せず空リストを返す。"""
    import urllib.error

    with patch("services.novel_db.character_extractor.urllib.request.urlopen") as urlopen:
        urlopen.side_effect = urllib.error.URLError("connection refused")
        result = extract_main_characters("これは十分に長い本文テキストです。" * 5)

    assert result == []
