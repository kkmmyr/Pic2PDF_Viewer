"""services/novel_db/qa_sessions.py の単体テスト（B-16）。

DB 入出力のみのテスト。LLM 呼び出しは含まない（router 側で別途モック化）。
"""

import pytest

from services.novel_db import with_db
from services.novel_db.migrations import upgrade_head
from services.novel_db.qa_sessions import (
    append_message,
    create_session,
    delete_session,
    get_session_detail,
    get_session_meta,
    list_sessions,
    load_chat_messages,
    update_session_title,
)
from services.novel_db.search import Scope


@pytest.fixture
def empty_db(tmp_data_dir):
    upgrade_head()
    return tmp_data_dir


def test_create_session_assigns_id_and_scope(empty_db):
    with with_db() as conn:
        sid = create_session(conn, Scope(type="book", id="x"), title="hello")
    with with_db() as conn:
        meta = get_session_meta(conn, sid)
    assert meta is not None
    assert meta.scope_type == "book"
    assert meta.scope_id == "x"
    assert meta.title == "hello"
    assert meta.message_count == 0


def test_append_message_records_role_and_meta(empty_db):
    with with_db() as conn:
        sid = create_session(conn, Scope(type="all", id=None))
        append_message(conn, sid, role="system", content="sys")
        append_message(conn, sid, role="user", content="Q1")
        append_message(
            conn,
            sid,
            role="assistant",
            content="A1",
            eval_count=42,
            done_reason="stop",
        )

    with with_db() as conn:
        detail = get_session_detail(conn, sid)
    assert detail is not None
    assert [m.role for m in detail.messages] == ["system", "user", "assistant"]
    assistant = detail.messages[2]
    assert assistant.eval_count == 42
    assert assistant.done_reason == "stop"


def test_load_chat_messages_returns_openai_format(empty_db):
    with with_db() as conn:
        sid = create_session(conn, Scope(type="book", id="b"))
        append_message(conn, sid, role="system", content="ctx")
        append_message(conn, sid, role="user", content="Q1")
        append_message(conn, sid, role="assistant", content="A1")
    with with_db() as conn:
        msgs = load_chat_messages(conn, sid)
    assert msgs == [
        {"role": "system", "content": "ctx"},
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1"},
    ]


def test_list_sessions_sorts_by_last_message_at_desc(empty_db):
    """活動順（last_message_at 降順）でセッションを返す。

    SQLite の datetime('now') は秒単位のため、`time.sleep(1.1)` で差をつける。
    """
    import time

    with with_db() as conn:
        s1 = create_session(conn, Scope(type="all", id=None), title="old")
        s2 = create_session(conn, Scope(type="book", id="b"), title="new")
        append_message(conn, s2, role="user", content="Q")
    time.sleep(1.1)
    with with_db() as conn:
        # s1 に後から追記 → s1 のほうが last_message_at は新しい
        append_message(conn, s1, role="user", content="Q")
    with with_db() as conn:
        items = list_sessions(conn)
    assert [s.id for s in items] == [s1, s2]


def test_delete_session_cascades_messages(empty_db):
    with with_db() as conn:
        sid = create_session(conn, Scope(type="all", id=None))
        append_message(conn, sid, role="user", content="Q1")
        append_message(conn, sid, role="assistant", content="A1")
    with with_db() as conn:
        ok = delete_session(conn, sid)
    assert ok is True
    with with_db() as conn:
        assert get_session_meta(conn, sid) is None
        # CASCADE で qa_messages も消える
        row = conn.execute(
            "SELECT COUNT(*) FROM qa_messages WHERE session_id = ?",
            (sid,),
        ).fetchone()
        assert row[0] == 0


def test_delete_session_returns_false_for_missing(empty_db):
    with with_db() as conn:
        assert delete_session(conn, 9999) is False


def test_update_session_title(empty_db):
    with with_db() as conn:
        sid = create_session(conn, Scope(type="all", id=None), title="old")
        update_session_title(conn, sid, "new title")
    with with_db() as conn:
        meta = get_session_meta(conn, sid)
    assert meta is not None
    assert meta.title == "new title"
