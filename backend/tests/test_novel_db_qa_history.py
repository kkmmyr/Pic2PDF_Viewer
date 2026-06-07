"""services/novel_db/qa_history.py の単体テスト。"""
import pytest

from services.novel_db import init_schema, with_db
from services.novel_db.qa_history import (
    delete_history,
    get_history_detail,
    list_history,
    save_error,
    save_finish,
    save_start,
)
from services.novel_db.search import Scope, SearchHit


@pytest.fixture
def history_db(tmp_data_dir):
    with with_db() as conn:
        init_schema(conn)


def _make_hit(book="book-1", page=1) -> SearchHit:
    return SearchHit(
        book_name=book,
        page_no=page,
        snippet="snippet text",
        has_highlight=False,
        image_url=f"/kindle_novel/images/{book}/001.png",
        rrf_score=0.05,
    )


def test_save_start_creates_row_with_empty_answer(history_db):
    with with_db() as conn:
        history_id = save_start(
            conn,
            scope=Scope(type="all"),
            question="Q?",
            prompt="prompt body",
            hits=[_make_hit()],
            model="gemma4:12b",
            options={"temperature": 0.2},
        )
    assert history_id > 0

    with with_db() as conn:
        detail = get_history_detail(conn, history_id)
    assert detail["question"] == "Q?"
    assert detail["answer"] == ""
    assert detail["prompt"] == "prompt body"
    assert detail["scope"] == {"type": "all", "id": None}
    assert detail["model"] == "gemma4:12b"
    assert detail["options"] == {"temperature": 0.2}
    assert len(detail["context"]) == 1
    assert detail["context"][0]["page_no"] == 1


def test_save_finish_updates_answer_and_done_reason(history_db):
    with with_db() as conn:
        history_id = save_start(
            conn,
            scope=Scope(type="all"),
            question="Q",
            prompt="P",
            hits=[],
            model="m",
            options={},
        )
        save_finish(conn, history_id, answer="A", done_reason="stop", eval_count=42)

    with with_db() as conn:
        detail = get_history_detail(conn, history_id)
    assert detail["answer"] == "A"
    assert detail["done_reason"] == "stop"
    assert detail["eval_count"] == 42
    assert detail["finished_at"] is not None


def test_save_error_records_error_message(history_db):
    with with_db() as conn:
        history_id = save_start(
            conn,
            scope=Scope(type="all"),
            question="Q",
            prompt="P",
            hits=[],
            model="m",
            options={},
        )
        save_error(conn, history_id, "boom")

    with with_db() as conn:
        detail = get_history_detail(conn, history_id)
    assert detail["error_message"] == "boom"
    assert detail["done_reason"] == "error"


def test_list_history_returns_descending_order(history_db):
    with with_db() as conn:
        h1 = save_start(conn, scope=Scope(type="all"), question="Q1",
                        prompt="P", hits=[], model="m", options={})
        h2 = save_start(conn, scope=Scope(type="all"), question="Q2",
                        prompt="P", hits=[], model="m", options={})
        save_finish(conn, h1, answer="A1", done_reason="stop", eval_count=1)
        save_finish(conn, h2, answer="A2", done_reason="stop", eval_count=2)

    with with_db() as conn:
        result = list_history(conn)
    assert result["total"] == 2
    # 新しいもの（h2 / Q2）が先頭
    assert result["items"][0]["question"] == "Q2"
    assert result["items"][1]["question"] == "Q1"
    assert "answer_preview" in result["items"][0]


def test_list_history_pagination(history_db):
    with with_db() as conn:
        for i in range(5):
            save_start(conn, scope=Scope(type="all"), question=f"Q{i}",
                       prompt="P", hits=[], model="m", options={})

    with with_db() as conn:
        first = list_history(conn, offset=0, limit=2)
        second = list_history(conn, offset=2, limit=2)
    assert len(first["items"]) == 2
    assert len(second["items"]) == 2
    assert first["total"] == 5
    # offset で取れる ID が異なる
    assert first["items"][0]["id"] != second["items"][0]["id"]


def test_list_history_answer_preview_truncates(history_db):
    long_answer = "あ" * 200
    with with_db() as conn:
        history_id = save_start(conn, scope=Scope(type="all"), question="Q",
                                prompt="P", hits=[], model="m", options={})
        save_finish(conn, history_id, answer=long_answer, done_reason="stop",
                    eval_count=None)

    with with_db() as conn:
        result = list_history(conn)
    preview = result["items"][0]["answer_preview"]
    assert preview.endswith("…")
    # 120 字 + 末尾の …
    assert len(preview) <= 121


def test_get_history_detail_returns_none_for_missing(history_db):
    with with_db() as conn:
        assert get_history_detail(conn, 99999) is None


def test_delete_history_removes_row(history_db):
    with with_db() as conn:
        history_id = save_start(conn, scope=Scope(type="all"), question="Q",
                                prompt="P", hits=[], model="m", options={})
        assert delete_history(conn, history_id) is True
        assert delete_history(conn, history_id) is False  # 二度目は False
        assert get_history_detail(conn, history_id) is None
