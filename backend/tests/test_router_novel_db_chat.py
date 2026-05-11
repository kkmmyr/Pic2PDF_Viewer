"""routers/novel_db.py のマルチターン会話 QA API（B-16）テスト。

LLM 呼び出しは `stream_chat` を monkeypatch して async generator を差し替える。
"""
import pytest

from services.novel_db import init_schema, with_db
from services.novel_db.qa_sessions import (
    append_message,
    create_session,
)
from services.novel_db.search import Scope


@pytest.fixture
def db_initialized(tmp_data_dir):
    with with_db() as conn:
        init_schema(conn)
    return tmp_data_dir


# ---------------------------------------------------------------------------
# GET /qa/sessions / detail / DELETE
# ---------------------------------------------------------------------------

def test_get_sessions_returns_empty_when_none(client, db_initialized):
    res = client.get("/api/novel_db/qa/sessions")
    assert res.status_code == 200
    assert res.json() == []


def test_get_sessions_returns_meta_with_message_count(client, db_initialized):
    with with_db() as conn:
        sid = create_session(conn, Scope(type="book", id="x"), title="T")
        append_message(conn, sid, role="user", content="Q")
        append_message(conn, sid, role="assistant", content="A")

    res = client.get("/api/novel_db/qa/sessions")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    item = body[0]
    assert item["scope_type"] == "book"
    assert item["scope_id"] == "x"
    assert item["title"] == "T"
    assert item["message_count"] == 2


def test_get_session_detail_excludes_system_messages(client, db_initialized):
    """詳細は user/assistant のみ。system は LLM 投入用なので UI には返さない。"""
    with with_db() as conn:
        sid = create_session(conn, Scope(type="all", id=None))
        append_message(conn, sid, role="system", content="ctx")
        append_message(conn, sid, role="user", content="Q1")
        append_message(conn, sid, role="assistant", content="A1")

    res = client.get(f"/api/novel_db/qa/sessions/{sid}")
    assert res.status_code == 200
    body = res.json()
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["user", "assistant"]


def test_get_session_detail_404_for_missing(client, db_initialized):
    res = client.get("/api/novel_db/qa/sessions/9999")
    assert res.status_code == 404


def test_delete_session_returns_204(client, db_initialized):
    with with_db() as conn:
        sid = create_session(conn, Scope(type="all", id=None))
    res = client.delete(f"/api/novel_db/qa/sessions/{sid}")
    assert res.status_code == 204
    # 削除後の取得は 404
    assert client.get(f"/api/novel_db/qa/sessions/{sid}").status_code == 404


def test_delete_session_404_for_missing(client, db_initialized):
    res = client.delete("/api/novel_db/qa/sessions/9999")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# title PATCH
# ---------------------------------------------------------------------------

def test_patch_title_updates(client, db_initialized):
    with with_db() as conn:
        sid = create_session(conn, Scope(type="all", id=None), title="old")
    res = client.patch(
        f"/api/novel_db/qa/sessions/{sid}/title", json={"title": "new"},
    )
    assert res.status_code == 204
    detail = client.get(f"/api/novel_db/qa/sessions/{sid}").json()
    assert detail["title"] == "new"


def test_patch_title_rejects_empty(client, db_initialized):
    with with_db() as conn:
        sid = create_session(conn, Scope(type="all", id=None))
    res = client.patch(
        f"/api/novel_db/qa/sessions/{sid}/title", json={"title": "   "},
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# POST /qa/sessions（初手 SSE）
#   - stream_chat を monkeypatch して 2 token + done を吐く async generator に差替
# ---------------------------------------------------------------------------

async def _fake_stream_chat(messages, **kwargs):
    """token + done を吐く最小ストリーム（テスト用）。"""
    yield {"response": "Hello"}
    yield {"response": " world"}
    yield {"done": True, "done_reason": "stop", "eval_count": 7}


def test_post_chat_session_start_creates_session_and_appends_assistant(
    client, db_initialized, monkeypatch,
):
    """初手 POST: session + system + user + assistant が DB に積まれる。"""
    # ハイブリッド検索を空ヒットにモック（テストで実検索を走らせない）
    monkeypatch.setattr(
        "routers.novel_db.hybrid_search", lambda *a, **kw: [],
    )
    monkeypatch.setattr(
        "routers.novel_db.expand_query", lambda q: [q],
    )
    monkeypatch.setattr(
        "routers.novel_db.search_book_summaries", lambda *a, **kw: [],
    )
    monkeypatch.setattr(
        "routers.novel_db.load_summaries_for_books", lambda *a, **kw: {},
    )
    monkeypatch.setattr("routers.novel_db.stream_chat", _fake_stream_chat)

    res = client.post(
        "/api/novel_db/qa/sessions",
        json={"scope": {"type": "all", "id": None}, "question": "テスト質問"},
    )
    assert res.status_code == 200
    # SSE body には token と done が並ぶ
    body = res.text
    assert '"token": "Hello"' in body
    assert '"done": true' in body
    assert '"session_id":' in body
    # DB に system + user + assistant が並んでいる
    with with_db() as conn:
        rows = conn.execute(
            "SELECT role, content FROM qa_messages ORDER BY id",
        ).fetchall()
    roles = [r[0] for r in rows]
    assert roles == ["system", "user", "assistant"]
    assert rows[1][1] == "テスト質問"
    assert rows[2][1] == "Hello world"


def test_post_chat_session_message_appends_user_and_assistant(
    client, db_initialized, monkeypatch,
):
    """続行 POST: 既存セッションに user + assistant が追記される。"""
    with with_db() as conn:
        sid = create_session(conn, Scope(type="all", id=None))
        append_message(conn, sid, role="system", content="ctx")
        append_message(conn, sid, role="user", content="Q1")
        append_message(conn, sid, role="assistant", content="A1")

    monkeypatch.setattr("routers.novel_db.stream_chat", _fake_stream_chat)

    res = client.post(
        f"/api/novel_db/qa/sessions/{sid}/messages",
        json={"question": "深掘り Q2"},
    )
    assert res.status_code == 200
    assert '"token": "Hello"' in res.text

    with with_db() as conn:
        rows = conn.execute(
            "SELECT role, content FROM qa_messages WHERE session_id = ? ORDER BY id",
            (sid,),
        ).fetchall()
    roles = [r[0] for r in rows]
    assert roles == ["system", "user", "assistant", "user", "assistant"]
    assert rows[3][1] == "深掘り Q2"


def test_post_chat_session_message_404_for_missing(client, db_initialized, monkeypatch):
    monkeypatch.setattr("routers.novel_db.stream_chat", _fake_stream_chat)
    res = client.post(
        "/api/novel_db/qa/sessions/9999/messages",
        json={"question": "x"},
    )
    assert res.status_code == 404
