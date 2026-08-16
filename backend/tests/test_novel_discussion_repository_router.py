"""Novel discussion repository and router contract tests."""

from __future__ import annotations

import json

import pytest

from services.novel_db.discussion_prompts import resolve_segment_titles
from services.novel_db.discussion_service import (
    MAX_INPUT_TOKENS,
    count_discussions,
    delete_discussion,
    list_discussions,
    save_discussion,
)
from services.novel_db.search import SearchHit


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

    directory = Path(tmp_data_dir["KINDLE_NOVEL_DIR"]) / "discussions"
    monkeypatch.setattr(svc, "DISCUSSIONS_DIR", directory)
    return directory


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
