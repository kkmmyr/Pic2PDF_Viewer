"""B-28 読書会ロングフォーム生成の単体テスト。

- discussion_prompts: 構成/台本メッセージ構築・共通プレフィックス一致・セグメント解決
- discussion_service: トークン推定・寛容パーサ・ストリーミング・plan パース・保存/一覧/削除
- router: SSE 2 段生成フロー・エラー SSE・DELETE エンドポイント（TestClient + monkeypatch）
"""

from __future__ import annotations

import json

import pytest

from services.novel_db.discussion_prompts import (
    SEGMENTS,
    build_plan_messages,
    build_script_messages,
    resolve_segment_titles,
)
from services.novel_db.discussion_service import (
    MAX_INPUT_TOKENS,
    _parse_turns_from_text,
    count_discussions,
    delete_discussion,
    estimate_book_tokens,
    format_book_text,
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


_PLAN = {
    "themes": [
        {"title": "喪失と再生", "question": "主人公の変化は成長か逃避か"},
        {"title": "円環構造", "question": "冒頭と結末の対応は何を意味するか"},
    ],
    "stances": {
        "a": "本作は構造で語る小説であり、円環構造こそ主題である。",
        "b": "主人公の感情の揺れこそが本体で、構造は後付けにすぎない。",
    },
    "cards": [
        {
            "title": "喪失文学の系譜",
            "content": "喪失を扱う近代文学の流れを紹介する。",
            "facts": ["『こころ』の作者は夏目漱石"],
            "keywords": ["こころ", "夏目漱石"],
        }
    ],
}


def _cast_snapshot() -> list[dict]:
    return [
        {"id": "rei", "marker": "A", "name": "レイ", "profile": "理屈屋", "stance": "構造派"},
        {"id": "mio", "marker": "B", "name": "ミオ", "profile": "直感派", "stance": "感情派"},
    ]


def _segments() -> list[dict]:
    return resolve_segment_titles(_PLAN)


@pytest.fixture
def discussions_dir(tmp_data_dir, monkeypatch):
    from pathlib import Path

    import services.novel_db.discussion_service as svc

    d = Path(tmp_data_dir["KINDLE_NOVEL_DIR"]) / "discussions"
    monkeypatch.setattr(svc, "DISCUSSIONS_DIR", d)
    return d


# ---------------------------------------------------------------------------
# estimate_book_tokens
# ---------------------------------------------------------------------------


def test_estimate_book_tokens_basic():
    hits = [_hit(1, "あ" * 1500), _hit(2, "い" * 1500)]
    # 3000 chars / 1.5 = 2000
    assert estimate_book_tokens(hits) == 2000


def test_estimate_book_tokens_empty():
    assert estimate_book_tokens([]) == 0


# ---------------------------------------------------------------------------
# discussion_prompts
# ---------------------------------------------------------------------------


def test_build_plan_messages_structure():
    book_text = format_book_text([_hit(1, "本文ページ1")])
    messages = build_plan_messages("テスト本", book_text)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    system = messages[0]["content"]
    assert "テスト本" in system
    assert "[page 1]" in system
    assert "本文ページ1" in system
    assert "レイ" in system
    assert "ミオ" in system
    assert '"themes"' in system
    assert "構成メモ" in messages[1]["content"]


def test_build_script_messages_structure():
    book_text = format_book_text([_hit(1, "本文ページ1")])
    messages = build_script_messages("テスト本", book_text, _PLAN)
    system = messages[0]["content"]
    # 構成メモの差し込み
    assert "喪失と再生" in system
    assert "円環構造" in system
    assert _PLAN["stances"]["a"] in system
    assert _PLAN["stances"]["b"] in system
    assert "喪失文学の系譜" in system
    assert "『こころ』の作者は夏目漱石" in system
    # セグメントマーカー指示
    for seg_id in ("op_hook", "theme1", "theme2", "tangent", "closing"):
        assert f"[S:{seg_id}]" in system
    assert "台本" in messages[1]["content"]


def test_plan_and_script_share_common_prefix():
    """KV cache 最適化: 2 呼び出しの system プロンプト先頭部分が完全一致する。"""
    book_text = format_book_text([_hit(1, "共通本文"), _hit(2, "続き")])
    plan_sys = build_plan_messages("本", book_text)[0]["content"]
    script_sys = build_script_messages("本", book_text, _PLAN)[0]["content"]
    marker = "## あなたの役割"
    assert plan_sys.split(marker)[0] == script_sys.split(marker)[0]
    assert book_text in plan_sys.split(marker)[0]


def test_resolve_segment_titles():
    segments = resolve_segment_titles(_PLAN)
    assert [s["id"] for s in segments] == [seg_id for seg_id, _ in SEGMENTS]
    by_id = {s["id"]: s["title"] for s in segments}
    assert by_id["op_hook"] == "OPフック"
    assert by_id["theme1"] == "喪失と再生"
    assert by_id["theme2"] == "円環構造"
    assert by_id["tangent"] == "脱線コーナー"
    assert by_id["closing"] == "締め"


# ---------------------------------------------------------------------------
# _parse_turns_from_text（寛容パーサ）
# ---------------------------------------------------------------------------


def test_parse_turns_basic():
    text = "[A]: 最初の発言。\n[B]: 応答の発言。\n[A]: 二回目の発言。"
    turns = _parse_turns_from_text(text)
    assert turns == [
        ("A", "最初の発言。"),
        ("B", "応答の発言。"),
        ("A", "二回目の発言。"),
    ]


def test_parse_turns_tolerant_marker_variants():
    """[A>: / [A]： / [A): などのドリフトを許容する。"""
    text = "[A]: 通常。\n[B>: 山括弧ドリフト。\n[A]： 全角コロン。\n[B): 丸括弧。\n[A: 閉じ括弧なし。"
    turns = _parse_turns_from_text(text)
    assert turns == [
        ("A", "通常。"),
        ("B", "山括弧ドリフト。"),
        ("A", "全角コロン。"),
        ("B", "丸括弧。"),
        ("A", "閉じ括弧なし。"),
    ]


def test_parse_turns_removes_segment_markers():
    text = "[S:op_hook]\n[A]: 発言1。\n[S:theme1]\n[B]: 発言2。"
    turns = _parse_turns_from_text(text)
    assert turns == [("A", "発言1。"), ("B", "発言2。")]
    for _, turn_text in turns:
        assert "[S" not in turn_text


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


def _fake_stream(tokens: list[str]):
    async def fake_astream_chat(messages, *, model=None, options=None):
        for t in tokens:
            yield {"response": t, "done": False}
        yield {"response": "", "done": True}

    return fake_astream_chat


async def _collect_events(monkeypatch, tokens: list[str]) -> list[dict]:
    from services.novel_db import discussion_service

    monkeypatch.setattr(discussion_service, "_astream_chat", _fake_stream(tokens))
    events = []
    async for ev in discussion_service.stream_discussion_turns([]):
        events.append(ev)
    return events


async def test_stream_emits_turns_and_segments(monkeypatch):
    events = await _collect_events(
        monkeypatch,
        [
            "[S:op_hook]\n[A]: レイの発言。",
            "\n[B]: ミオの発言。",
            "\n[S:theme1]\n[A]: テーマ1の発言。",
        ],
    )
    assert events == [
        {"type": "segment", "id": "op_hook"},
        {"type": "turn", "speaker": "A", "text": "レイの発言。", "segment": "op_hook"},
        {"type": "turn", "speaker": "B", "text": "ミオの発言。", "segment": "op_hook"},
        {"type": "segment", "id": "theme1"},
        {"type": "turn", "speaker": "A", "text": "テーマ1の発言。", "segment": "theme1"},
    ]


async def test_stream_segment_marker_split_across_chunks(monkeypatch):
    """セグメントマーカーがチャンク境界で分断されても ID を取り違えない。"""
    events = await _collect_events(
        monkeypatch,
        ["[S:the", "me1]\n[A]: 発言。"],
    )
    assert events == [
        {"type": "segment", "id": "theme1"},
        {"type": "turn", "speaker": "A", "text": "発言。", "segment": "theme1"},
    ]


async def test_stream_turn_marker_removed_from_text(monkeypatch):
    """セグメントマーカー行が turn text に混入しない。"""
    events = await _collect_events(
        monkeypatch,
        ["[S:op_hook]\n[A]: 発言その1。\n[S:closing]\n[B]: 締めの発言。"],
    )
    turn_texts = [e["text"] for e in events if e["type"] == "turn"]
    assert all("[S" not in t for t in turn_texts)
    assert turn_texts == ["発言その1。", "締めの発言。"]


async def test_stream_without_segments_yields_none_segment(monkeypatch):
    events = await _collect_events(monkeypatch, ["[A]: 唯一の発言。"])
    assert events == [{"type": "turn", "speaker": "A", "text": "唯一の発言。", "segment": None}]


# ---------------------------------------------------------------------------
# generate_plan
# ---------------------------------------------------------------------------


async def _run_generate_plan(monkeypatch, llm_output: str) -> dict:
    from services.novel_db import discussion_service

    monkeypatch.setattr(discussion_service, "_astream_chat", _fake_stream([llm_output]))
    return await discussion_service.generate_plan([])


async def test_generate_plan_parses_plain_json(monkeypatch):
    plan = await _run_generate_plan(monkeypatch, json.dumps(_PLAN, ensure_ascii=False))
    assert plan["themes"][0]["title"] == "喪失と再生"
    assert plan["stances"]["a"]
    assert len(plan["cards"]) == 1


async def test_generate_plan_strips_code_fence(monkeypatch):
    output = "```json\n" + json.dumps(_PLAN, ensure_ascii=False) + "\n```"
    plan = await _run_generate_plan(monkeypatch, output)
    assert plan["themes"][1]["title"] == "円環構造"


async def test_generate_plan_ignores_preamble(monkeypatch):
    output = "はい、構成メモを作成しました。\n" + json.dumps(_PLAN, ensure_ascii=False) + "\n以上です。"
    plan = await _run_generate_plan(monkeypatch, output)
    assert plan["stances"]["b"]


async def test_generate_plan_invalid_json_raises(monkeypatch):
    with pytest.raises(ValueError):
        await _run_generate_plan(monkeypatch, "{ themes: 壊れたJSON }")


async def test_generate_plan_missing_themes_raises(monkeypatch):
    broken = {**_PLAN, "themes": [{"title": "1件だけ", "question": "?"}]}
    with pytest.raises(ValueError, match="themes"):
        await _run_generate_plan(monkeypatch, json.dumps(broken, ensure_ascii=False))


async def test_generate_plan_no_json_raises(monkeypatch):
    with pytest.raises(ValueError):
        await _run_generate_plan(monkeypatch, "JSONを含まないテキスト")


async def test_generate_plan_retries_on_broken_json(monkeypatch):
    """1 回目が JSON 崩れでも 2 回目で正常 JSON が返れば成功する。"""
    from services.novel_db import discussion_service

    outputs = iter(["{ themes: 壊れたJSON }", json.dumps(_PLAN, ensure_ascii=False)])

    async def fake_astream_chat(messages, *, model=None, options=None):
        yield {"response": next(outputs), "done": False}
        yield {"response": "", "done": True}

    monkeypatch.setattr(discussion_service, "_astream_chat", fake_astream_chat)
    plan = await discussion_service.generate_plan([])
    assert plan["themes"][0]["title"] == "喪失と再生"


async def test_generate_plan_exhausts_retries(monkeypatch):
    """全試行が JSON 崩れなら最後の ValueError を送出し、試行回数は上限どおり。"""
    from services.novel_db import discussion_service

    calls = {"n": 0}

    async def fake_astream_chat(messages, *, model=None, options=None):
        calls["n"] += 1
        yield {"response": "{ themes: 壊れたJSON }", "done": False}
        yield {"response": "", "done": True}

    monkeypatch.setattr(discussion_service, "_astream_chat", fake_astream_chat)
    with pytest.raises(ValueError, match="JSON パースに失敗"):
        await discussion_service.generate_plan([])
    assert calls["n"] == discussion_service._PLAN_MAX_ATTEMPTS


# ---------------------------------------------------------------------------
# save_discussion v2 / list_discussions / delete_discussion
# ---------------------------------------------------------------------------


def _sample_turns() -> list[dict]:
    return [
        {"speaker": "A", "text": "発言A", "segment": "op_hook"},
        {"speaker": "B", "text": "発言B", "segment": "op_hook"},
    ]


def _sample_checks() -> dict:
    return {"passed": True, "results": [{"id": "M1", "label": "字数", "passed": True, "detail": ""}]}


def test_save_v2_and_list(discussions_dir):
    path = save_discussion(
        "test-book",
        _cast_snapshot(),
        _segments(),
        _PLAN["cards"],
        _sample_turns(),
        _sample_checks(),
    )
    assert path.endswith(".json")
    # タイムスタンプが +0900 サフィックス（旧実装は JST 値に Z を付ける不整合があった）
    from pathlib import Path

    assert "+0900" in Path(path).name
    assert "Z" not in Path(path).name

    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    assert saved["format_version"] == 2
    assert saved["cast"][0]["name"] == "レイ"
    assert saved["partial"] is False

    items = list_discussions("test-book")
    assert len(items) == 1
    item = items[0]
    assert item["format_version"] == 2
    assert item["turn_count"] == 2
    # v2 の personas は cast から合成（name + stance）
    assert item["personas"] == [
        {"name": "レイ", "style_description": "構造派"},
        {"name": "ミオ", "style_description": "感情派"},
    ]
    assert item["segments"][0] == {"id": "op_hook", "title": "OPフック"}
    assert item["checks"]["passed"] is True
    assert item["turns"][0]["segment"] == "op_hook"


def test_list_reads_v1_format(discussions_dir):
    """旧 B-20 形式（format_version なし）も壊れず読める。"""
    book_dir = discussions_dir / "old-book"
    book_dir.mkdir(parents=True)
    v1_data = {
        "book": "old-book",
        "personas": [
            {"name": "批評家", "style_description": "論理的"},
            {"name": "ファン", "style_description": "感情的"},
        ],
        "turns": [{"speaker": "A", "text": "旧形式の発言"}],
        "partial": False,
        "created_at": "2026-05-01T00:00:00+09:00",
    }
    (book_dir / "20260501T000000Z.json").write_text(json.dumps(v1_data, ensure_ascii=False), encoding="utf-8")

    items = list_discussions("old-book")
    assert len(items) == 1
    item = items[0]
    assert item["format_version"] == 1
    assert item["personas"][0]["name"] == "批評家"
    assert item["turn_count"] == 1
    assert item["segments"] is None
    assert item["checks"] is None


def test_list_discussions_empty_when_no_dir(discussions_dir):
    assert list_discussions("nonexistent-book") == []


def test_delete_discussion_success(discussions_dir):
    path = save_discussion(
        "test-book", _cast_snapshot(), _segments(), _PLAN["cards"], _sample_turns(), _sample_checks()
    )
    from pathlib import Path

    filename = Path(path).name
    assert delete_discussion("test-book", filename) is True
    assert not Path(path).exists()


def test_delete_discussion_not_found(discussions_dir):
    assert delete_discussion("test-book", "20990101T000000+0900.json") is False


def test_delete_discussion_rejects_bad_filename(discussions_dir):
    with pytest.raises(ValueError):
        delete_discussion("test-book", "../../../etc/passwd")
    with pytest.raises(ValueError):
        delete_discussion("test-book", "note.txt")


def test_delete_discussion_rejects_traversal_book_name(discussions_dir):
    (discussions_dir / "victim.json").parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError):
        delete_discussion("..", "victim.json")


@pytest.mark.parametrize("book_name", ["../outside", "C:/Windows", "C:\\Windows"])
def test_discussion_reads_and_writes_reject_unsafe_book_name(discussions_dir, book_name):
    with pytest.raises(ValueError):
        count_discussions(book_name)
    with pytest.raises(ValueError):
        list_discussions(book_name)
    with pytest.raises(ValueError):
        save_discussion(book_name, _cast_snapshot(), _segments(), _PLAN["cards"], [], _sample_checks())


# ---------------------------------------------------------------------------
# router: generate SSE フロー
# ---------------------------------------------------------------------------


def _parse_sse(text: str) -> list[dict]:
    return [json.loads(line[len("data: ") :]) for line in text.splitlines() if line.startswith("data: ")]


def test_generate_token_overflow_returns_error_sse(client, monkeypatch):
    """本文が MAX_INPUT_TOKENS を超えるときエラー SSE が返る。"""
    import routers.novel_discussion as disc_router

    huge_text = "あ" * int(MAX_INPUT_TOKENS * 1.5 * 1.5 + 100)
    fake_hit = _hit(1, huge_text)
    monkeypatch.setattr(disc_router, "load_all_pages_of_book", lambda *a, **kw: [fake_hit])

    resp = client.post("/api/novel/discussion/generate", json={"book_name": "test-book"})
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert events[0]["type"] == "error"
    assert "長すぎます" in events[0]["message"]


def test_generate_rejects_unsafe_book_name_before_streaming(client):
    resp = client.post("/api/novel/discussion/generate", json={"book_name": "C:/Windows"})
    assert resp.status_code == 400


def test_history_rejects_unsafe_book_name(client):
    resp = client.get("/api/novel/discussion/history", params={"book_name": "../outside"})
    assert resp.status_code == 400


def test_generate_no_pages_returns_error_sse(client, monkeypatch):
    """インデックスが空のときエラー SSE が返る。"""
    import routers.novel_discussion as disc_router

    monkeypatch.setattr(disc_router, "load_all_pages_of_book", lambda *a, **kw: [])

    resp = client.post("/api/novel/discussion/generate", json={"book_name": "missing-book"})
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert events[0]["type"] == "error"
    assert "ページデータが見つかりません" in events[0]["message"]


def test_generate_full_flow_sse(client, monkeypatch, tmp_data_dir):
    """planning → scripting → segment/turn → done（checks 付き）の一連の SSE を検証する。"""
    from pathlib import Path

    import routers.novel_discussion as disc_router
    import services.novel_db.discussion_service as svc

    monkeypatch.setattr(svc, "DISCUSSIONS_DIR", Path(tmp_data_dir["KINDLE_NOVEL_DIR"]) / "discussions")
    monkeypatch.setattr(disc_router, "load_all_pages_of_book", lambda *a, **kw: [_hit(1, "本文")])

    async def fake_generate_plan(messages, **kwargs):
        return _PLAN

    async def fake_stream(messages, **kwargs):
        yield {"type": "segment", "id": "op_hook"}
        yield {"type": "turn", "speaker": "A", "text": "こころが刺さる。", "segment": "op_hook"}
        yield {"type": "turn", "speaker": "B", "text": "わかる。", "segment": "op_hook"}

    monkeypatch.setattr(disc_router, "generate_plan", fake_generate_plan)
    monkeypatch.setattr(disc_router, "stream_discussion_turns", fake_stream)

    resp = client.post("/api/novel/discussion/generate", json={"book_name": "test-book"})
    assert resp.status_code == 200
    events = _parse_sse(resp.text)

    assert events[0] == {"type": "status", "stage": "planning"}
    assert events[1] == {"type": "status", "stage": "scripting"}
    assert events[2] == {"type": "segment", "id": "op_hook", "title": "OPフック"}
    assert events[3]["type"] == "turn"
    assert events[3]["segment"] == "op_hook"
    done = events[-1]
    assert done["type"] == "done"
    assert done["saved_path"].endswith(".json")
    # 2 ターン・セグメント不足なので機械チェックは不合格（結果が含まれることを確認）
    assert done["checks"]["passed"] is False
    check_ids = [r["id"] for r in done["checks"]["results"]]
    assert check_ids == ["M1", "M2", "M3", "M4", "M5"]

    # 保存 JSON が v2 形式で読み戻せる
    items = list_discussions("test-book")
    assert items[0]["format_version"] == 2
    assert items[0]["checks"]["passed"] is False


def test_generate_plan_failure_returns_error_sse(client, monkeypatch):
    import routers.novel_discussion as disc_router

    monkeypatch.setattr(disc_router, "load_all_pages_of_book", lambda *a, **kw: [_hit(1, "本文")])

    async def failing_plan(messages, **kwargs):
        raise ValueError("構成メモの JSON パースに失敗しました")

    monkeypatch.setattr(disc_router, "generate_plan", failing_plan)

    resp = client.post("/api/novel/discussion/generate", json={"book_name": "test-book"})
    events = _parse_sse(resp.text)
    assert events[0] == {"type": "status", "stage": "planning"}
    assert events[1]["type"] == "error"
    assert "構成メモ" in events[1]["message"]


# ---------------------------------------------------------------------------
# router: DELETE /novel/discussion/history/{filename}
# ---------------------------------------------------------------------------


def test_delete_history_success(client, monkeypatch, tmp_data_dir):
    from pathlib import Path

    import services.novel_db.discussion_service as svc

    monkeypatch.setattr(svc, "DISCUSSIONS_DIR", Path(tmp_data_dir["KINDLE_NOVEL_DIR"]) / "discussions")
    path = save_discussion(
        "test-book", _cast_snapshot(), _segments(), _PLAN["cards"], _sample_turns(), _sample_checks()
    )
    filename = Path(path).name

    resp = client.delete(f"/api/novel/discussion/history/{filename}", params={"book_name": "test-book"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted"}
    assert not Path(path).exists()


def test_delete_history_not_found(client, monkeypatch, tmp_data_dir):
    from pathlib import Path

    import services.novel_db.discussion_service as svc

    monkeypatch.setattr(svc, "DISCUSSIONS_DIR", Path(tmp_data_dir["KINDLE_NOVEL_DIR"]) / "discussions")
    resp = client.delete(
        "/api/novel/discussion/history/20990101T000000+0900.json",
        params={"book_name": "test-book"},
    )
    assert resp.status_code == 404


def test_delete_history_bad_filename(client, monkeypatch, tmp_data_dir):
    from pathlib import Path

    import services.novel_db.discussion_service as svc

    monkeypatch.setattr(svc, "DISCUSSIONS_DIR", Path(tmp_data_dir["KINDLE_NOVEL_DIR"]) / "discussions")
    resp = client.delete("/api/novel/discussion/history/bad..name.txt", params={"book_name": "test-book"})
    assert resp.status_code == 400
