"""B-28 DoD 層1 機械チェック（M1〜M5）の単体テスト。"""

from __future__ import annotations

from services.novel_db.discussion_checks import run_checks

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

_ALL_SEGMENTS = ["op_hook", "theme1", "theme2", "tangent", "closing"]

_CARDS = [
    {
        "title": "喪失文学の系譜",
        "content": "近代文学の話。",
        "facts": ["『こころ』の作者は夏目漱石"],
        "keywords": ["こころ", "夏目漱石"],
    },
    {
        "title": "数学小話",
        "content": "無限の話。",
        "facts": [],
        "keywords": ["無限", "集合論"],
    },
]


def _passing_turns() -> list[dict]:
    """M1〜M5 すべて合格するターン列（16 ターン × 250 字 = 4,000 字、キーワード含む）。"""
    turns = []
    for i in range(16):
        speaker = "A" if i % 2 == 0 else "B"
        text = ("この作品の構造について語る。" + "あ" * 236)[:250]
        turns.append({"speaker": speaker, "text": text, "segment": "theme1"})
    # 1 ターンにネタカードのキーワードを混ぜる（字数は 250 のまま）
    turns[10]["text"] = ("夏目漱石の話に接続すると面白い。" + "い" * 234)[:250]
    return turns


def _result(checks: dict, check_id: str) -> dict:
    return next(r for r in checks["results"] if r["id"] == check_id)


# ---------------------------------------------------------------------------
# 全体
# ---------------------------------------------------------------------------


def test_all_checks_pass():
    checks = run_checks(_passing_turns(), _ALL_SEGMENTS, _CARDS)
    assert checks["passed"] is True
    assert [r["id"] for r in checks["results"]] == ["M1", "M2", "M3", "M4", "M5"]
    assert all(r["passed"] for r in checks["results"])
    assert all(r["label"] for r in checks["results"])


# ---------------------------------------------------------------------------
# M1: 字数
# ---------------------------------------------------------------------------


def test_m1_fails_too_short():
    turns = [{"speaker": "A", "text": "短い。", "segment": None}] * 16
    checks = run_checks(turns, _ALL_SEGMENTS, _CARDS)
    m1 = _result(checks, "M1")
    assert m1["passed"] is False
    assert "字" in m1["detail"]


def test_m1_fails_too_long():
    turns = [{"speaker": "A", "text": "あ" * 300, "segment": None} for _ in range(16)]
    # 4,800 字 > 4,500
    checks = run_checks(turns, _ALL_SEGMENTS, _CARDS)
    assert _result(checks, "M1")["passed"] is False


def test_m1_counts_turn_text_only():
    """合計はターン text の文字数ベース（16 ターン × 250 字 + 改行分は含まない）。"""
    turns = _passing_turns()
    checks = run_checks(turns, _ALL_SEGMENTS, _CARDS)
    m1 = _result(checks, "M1")
    assert m1["passed"] is True


# ---------------------------------------------------------------------------
# M2: セグメント出現
# ---------------------------------------------------------------------------


def test_m2_fails_when_segment_missing():
    seen = ["op_hook", "theme1", "theme2", "closing"]  # tangent 欠落
    checks = run_checks(_passing_turns(), seen, _CARDS)
    m2 = _result(checks, "M2")
    assert m2["passed"] is False
    assert "tangent" in m2["detail"]


def test_m2_passes_with_duplicates_and_extras():
    seen = _ALL_SEGMENTS + ["theme1", "unknown_extra"]
    checks = run_checks(_passing_turns(), seen, _CARDS)
    assert _result(checks, "M2")["passed"] is True


# ---------------------------------------------------------------------------
# M3: 話者分割
# ---------------------------------------------------------------------------


def test_m3_fails_too_few_turns():
    turns = _passing_turns()[:14]
    checks = run_checks(turns, _ALL_SEGMENTS, _CARDS)
    m3 = _result(checks, "M3")
    assert m3["passed"] is False
    assert "14" in m3["detail"]


def test_m3_fails_on_marker_residue():
    turns = _passing_turns()
    turns[3]["text"] = "残骸あり [B]: の断片" + "あ" * 200
    checks = run_checks(turns, _ALL_SEGMENTS, _CARDS)
    m3 = _result(checks, "M3")
    assert m3["passed"] is False
    assert "残骸" in m3["detail"]


def test_m3_fails_on_segment_residue():
    turns = _passing_turns()
    turns[5]["text"] = "セグメント残骸 [S:theme1] を含む" + "あ" * 200
    assert _result(run_checks(turns, _ALL_SEGMENTS, _CARDS), "M3")["passed"] is False


def test_m3_fails_on_overlong_turn():
    turns = _passing_turns()[:15]
    turns[0]["text"] = "あ" * 601
    checks = run_checks(turns, _ALL_SEGMENTS, _CARDS)
    m3 = _result(checks, "M3")
    assert m3["passed"] is False
    assert "601" in m3["detail"]


# ---------------------------------------------------------------------------
# M4: 言語リーク
# ---------------------------------------------------------------------------


def test_m4_detects_simplified_chinese_chars():
    turns = _passing_turns()
    turns[2]["text"] = ("这は简体字リーク、们も变もダメ。" + "あ" * 230)[:250]
    checks = run_checks(turns, _ALL_SEGMENTS, _CARDS)
    m4 = _result(checks, "M4")
    assert m4["passed"] is False
    assert "这" in m4["detail"]
    assert "们" in m4["detail"]
    assert "变" in m4["detail"]


def test_m4_detects_english_word_leak():
    turns = _passing_turns()
    turns[4]["text"] = ("ここで Amazing な展開になる。" + "あ" * 230)[:250]
    checks = run_checks(turns, _ALL_SEGMENTS, _CARDS)
    m4 = _result(checks, "M4")
    assert m4["passed"] is False
    assert "Amazing" in m4["detail"]


def test_m4_allows_short_latin_abbreviations():
    """OP / ED / SF など 3 文字以下の英字は許容される。"""
    turns = _passing_turns()
    turns[6]["text"] = ("OPの掴みとEDの余韻、SF的な設定の話。" + "あ" * 230)[:250]
    checks = run_checks(turns, _ALL_SEGMENTS, _CARDS)
    assert _result(checks, "M4")["passed"] is True


def test_m4_allows_registered_english_titles():
    """登録済みの英語作品名は言語リーク扱いしない。"""
    turns = _passing_turns()
    turns[6]["text"] = ("BLEACHとFate/Grand Orderを例に挙げる。" + "あ" * 220)[:250]
    checks = run_checks(turns, _ALL_SEGMENTS, _CARDS)
    assert _result(checks, "M4")["passed"] is True


def test_m4_does_not_flag_japanese_shinjitai():
    """新字体と同形の字（学・国・会・写・体 等）は簡体字扱いしない。"""
    turns = _passing_turns()
    turns[7]["text"] = ("学校と国と会社で写真の話。体と万と与も問題ない。" + "あ" * 226)[:250]
    checks = run_checks(turns, _ALL_SEGMENTS, _CARDS)
    assert _result(checks, "M4")["passed"] is True


# ---------------------------------------------------------------------------
# M5: ネタカード言及
# ---------------------------------------------------------------------------


def test_m5_fails_when_no_keyword_mentioned():
    turns = [{"speaker": "A", "text": "カードと無関係な話。" + "あ" * 240, "segment": None} for _ in range(16)]
    checks = run_checks(turns, _ALL_SEGMENTS, _CARDS)
    m5 = _result(checks, "M5")
    assert m5["passed"] is False


def test_m5_passes_with_any_card_keyword():
    turns = _passing_turns()
    checks = run_checks(turns, _ALL_SEGMENTS, _CARDS)
    m5 = _result(checks, "M5")
    assert m5["passed"] is True
    assert "夏目漱石" in m5["detail"]


def test_m5_fails_with_empty_cards():
    checks = run_checks(_passing_turns(), _ALL_SEGMENTS, [])
    assert _result(checks, "M5")["passed"] is False
