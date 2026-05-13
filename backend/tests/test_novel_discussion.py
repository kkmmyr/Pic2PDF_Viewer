"""B-20 読書会ディスカッション生成の単体テスト。

- discussion_service: トークン推定・メッセージ構築・ターンパース・保存/一覧
- router: SSE ストリーミング・トークン超過エラー（TestClient + monkeypatch）
"""
from __future__ import annotations

import json

import pytest

from services.novel_db.discussion_service import (
    MAX_INPUT_TOKENS,
    Persona,
    _parse_turns_from_text,
    build_messages,
    estimate_book_tokens,
    list_discussions,
    save_discussion,
)
from services.novel_db.search import SearchHit


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _hit(page: int, text: str = "本文テスト") -> SearchHit:
    return SearchHit(
        book_name="test-book",
        page_no=page,
        snippet=text,
        has_highlight=False,
        image_url=None,
        rrf_score=0.5,
    )


_PERSONA_A = Persona(name="批評家", style_description="論理的・敬語")
_PERSONA_B = Persona(name="ファン", style_description="感情的・フランク")


# ---------------------------------------------------------------------------
# estimate_book_tokens
# ---------------------------------------------------------------------------

def test_estimate_book_tokens_basic():
    hits = [_hit(1, "あ" * 1500), _hit(2, "い" * 1500)]
    tokens = estimate_book_tokens(hits)
    # 3000 chars / 1.5 = 2000
    assert tokens == 2000


def test_estimate_book_tokens_empty():
    assert estimate_book_tokens([]) == 0


# ---------------------------------------------------------------------------
# build_messages
# ---------------------------------------------------------------------------

def test_build_messages_structure():
    hits = [_hit(1, "本文ページ1"), _hit(2, "本文ページ2")]
    messages = build_messages("テスト本", _PERSONA_A, _PERSONA_B, 6, hits)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    system = messages[0]["content"]
    assert "テスト本" in system
    assert "批評家" in system
    assert "ファン" in system
    assert "[A]:" in system
    assert "[B]:" in system
    assert "6" in system
    assert "[page 1]" in system
    assert "本文ページ1" in system


def test_build_messages_num_turns_in_user():
    hits = [_hit(1)]
    messages = build_messages("本", _PERSONA_A, _PERSONA_B, 10, hits)
    assert "10" in messages[1]["content"]


# ---------------------------------------------------------------------------
# _parse_turns_from_text（内部ロジック）
# ---------------------------------------------------------------------------

def test_parse_turns_basic():
    text = "[A]: 最初の発言。\n[B]: 応答の発言。\n[A]: 二回目の発言。"
    turns = _parse_turns_from_text(text)
    assert len(turns) == 3
    assert turns[0] == ("A", "最初の発言。")
    assert turns[1] == ("B", "応答の発言。")
    assert turns[2] == ("A", "二回目の発言。")


def test_parse_turns_strips_whitespace():
    text = "[A]:   スペースあり。  \n[B]:  \n  テキスト。  "
    turns = _parse_turns_from_text(text)
    assert turns[0][1] == "スペースあり。"
    assert turns[1][1] == "テキスト。"


def test_parse_turns_ignores_prefix_before_first_marker():
    text = "（前置き無視）\n[A]: 本文発言。\n[B]: 応答。"
    turns = _parse_turns_from_text(text)
    assert len(turns) == 2
    assert turns[0] == ("A", "本文発言。")


def test_parse_turns_empty_text():
    assert _parse_turns_from_text("") == []


def test_parse_turns_no_markers():
    assert _parse_turns_from_text("何もマーカーがない") == []


# ---------------------------------------------------------------------------
# stream_discussion_turns（monkeypatch）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_discussion_turns_emits_turns(monkeypatch):
    from services.novel_db import discussion_service

    async def fake_astream_chat(messages, *, model=None, options=None):
        # LLM が [A]: / [B]: 形式で出力するシミュレーション
        tokens = [
            "[A]: 批評家の発言。",
            "\n[B]: ファンの発言。",
            "\n[A]: 続きの発言。",
        ]
        for t in tokens:
            yield {"response": t, "done": False}
        yield {"response": "", "done": True}

    monkeypatch.setattr(discussion_service, "_astream_chat", fake_astream_chat)

    events = []
    async for ev in discussion_service.stream_discussion_turns([]):
        events.append(ev)

    assert len(events) == 3
    assert events[0] == {"type": "turn", "speaker": "A", "text": "批評家の発言。"}
    assert events[1] == {"type": "turn", "speaker": "B", "text": "ファンの発言。"}
    assert events[2] == {"type": "turn", "speaker": "A", "text": "続きの発言。"}


@pytest.mark.asyncio
async def test_stream_discussion_turns_single_turn(monkeypatch):
    from services.novel_db import discussion_service

    async def fake_astream_chat(messages, *, model=None, options=None):
        yield {"response": "[A]: 唯一の発言。", "done": False}
        yield {"response": "", "done": True}

    monkeypatch.setattr(discussion_service, "_astream_chat", fake_astream_chat)

    events = []
    async for ev in discussion_service.stream_discussion_turns([]):
        events.append(ev)

    assert len(events) == 1
    assert events[0]["speaker"] == "A"
    assert events[0]["text"] == "唯一の発言。"


# ---------------------------------------------------------------------------
# save_discussion / list_discussions
# ---------------------------------------------------------------------------

def test_save_and_list_discussion(tmp_data_dir, monkeypatch):
    import services.novel_db.discussion_service as svc
    from pathlib import Path

    discussions_dir = Path(tmp_data_dir["KINDLE_NOVEL_DIR"]) / "discussions"
    monkeypatch.setattr(svc, "DISCUSSIONS_DIR", discussions_dir)

    turns = [
        {"speaker": "A", "text": "発言A"},
        {"speaker": "B", "text": "発言B"},
    ]
    path = save_discussion("test-book", _PERSONA_A, _PERSONA_B, turns)
    assert path.endswith(".json")

    items = list_discussions("test-book")
    assert len(items) == 1
    assert items[0]["turn_count"] == 2
    assert items[0]["personas"][0]["name"] == "批評家"
    assert items[0]["turns"][0]["text"] == "発言A"


def test_list_discussions_empty_when_no_dir(tmp_data_dir, monkeypatch):
    import services.novel_db.discussion_service as svc
    from pathlib import Path

    discussions_dir = Path(tmp_data_dir["KINDLE_NOVEL_DIR"]) / "discussions"
    monkeypatch.setattr(svc, "DISCUSSIONS_DIR", discussions_dir)

    assert list_discussions("nonexistent-book") == []


# ---------------------------------------------------------------------------
# router: トークン超過エラー
# ---------------------------------------------------------------------------

def test_generate_token_overflow_returns_error_sse(client, monkeypatch):
    """本文が MAX_INPUT_TOKENS を超えるときエラー SSE が返る。"""
    from services.novel_db.search import SearchHit

    # ルーターは `from services.novel_db.search import load_all_pages_of_book` で
    # キャプチャしているため、routers.novel_discussion 側を差し替える
    import routers.novel_discussion as disc_router

    huge_text = "あ" * int(MAX_INPUT_TOKENS * 1.5 * 1.5 + 100)
    fake_hit = SearchHit(
        book_name="test-book",
        page_no=1,
        snippet=huge_text,
        has_highlight=False,
        image_url=None,
        rrf_score=1.0,
    )
    monkeypatch.setattr(disc_router, "load_all_pages_of_book", lambda *a, **kw: [fake_hit])

    payload = {
        "book_name": "test-book",
        "personas": [
            {"name": "A", "style_description": "批評家"},
            {"name": "B", "style_description": "ファン"},
        ],
        "num_turns": 6,
    }
    resp = client.post("/api/novel/discussion/generate", json=payload)
    assert resp.status_code == 200
    parsed = json.loads(resp.text.replace("data: ", "").strip())
    assert parsed["type"] == "error"
    assert "長すぎます" in parsed["message"]


def test_generate_no_pages_returns_error_sse(client, monkeypatch):
    """インデックスが空のときエラー SSE が返る。"""
    import routers.novel_discussion as disc_router
    monkeypatch.setattr(disc_router, "load_all_pages_of_book", lambda *a, **kw: [])

    payload = {
        "book_name": "missing-book",
        "personas": [
            {"name": "A", "style_description": "x"},
            {"name": "B", "style_description": "y"},
        ],
        "num_turns": 4,
    }
    resp = client.post("/api/novel/discussion/generate", json=payload)
    assert resp.status_code == 200
    parsed = json.loads(resp.text.replace("data: ", "").strip())
    assert parsed["type"] == "error"
    assert "ページデータが見つかりません" in parsed["message"]
