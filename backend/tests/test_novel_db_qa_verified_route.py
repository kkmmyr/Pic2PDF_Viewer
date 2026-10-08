"""The SSE boundary must not expose unverified or stale quotes."""

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from routers.novel_db import qa
from routers.novel_db.schemas import QaRequest


@pytest.fixture
def route(monkeypatch):
    conn = Mock()

    @contextmanager
    def database():
        yield conn

    snapshot = SimpleNamespace(sources=(), body_versions={"book": {"body_sha256": "sealed"}})
    monkeypatch.setattr(qa, "with_db", database)
    monkeypatch.setattr(qa, "retrieve", lambda *args: SimpleNamespace(hits=[], qa_options={}, book_summaries=[]))
    monkeypatch.setattr(qa, "freeze_qa_sources", lambda *args: snapshot)
    monkeypatch.setattr(qa, "build_grounded_prompt", lambda *args: "prompt")
    monkeypatch.setattr(qa.novel_db_settings, "NOVEL_DB_QA_RESPONSE_MODE", "verified_quotes")
    checked = Mock()
    finish, error, start = Mock(), Mock(), Mock(return_value=7)
    monkeypatch.setattr(qa, "assert_qa_sources_current", checked)
    monkeypatch.setattr(qa, "save_start", start)
    monkeypatch.setattr(qa, "save_finish", finish)
    monkeypatch.setattr(qa, "save_error", error)
    return SimpleNamespace(conn=conn, checked=checked, finish=finish, error=error, start=start)


class Request:
    def __init__(self, disconnected=False):
        self.disconnected = disconnected

    async def is_disconnected(self):
        return self.disconnected


async def response(request=None):
    return await qa.post_qa(QaRequest(question="何ですか", scope={"type": "book", "id": "book"}), request or Request())


@pytest.mark.asyncio
async def test_quote_is_emitted_only_after_version_check_and_history_finish(route, monkeypatch):
    async def generate(*args, **kwargs):
        yield {"pending": True}
        yield {"response": "canonical quote"}
        yield {"done": True, "done_reason": "stop", "validation_attempts": [{"attempt": 1, "passed": True}]}

    monkeypatch.setattr(qa, "stream_verified_quotes", generate)
    stream = (await response()).body_iterator
    assert await anext(stream) == ": keep-alive\n\n"
    token = await anext(stream)
    assert "canonical quote" in token
    route.checked.assert_called_once()
    route.conn.execute.assert_called_once_with("BEGIN IMMEDIATE")
    assert route.finish.call_args.kwargs["validation_attempts"] == [{"attempt": 1, "passed": True}]
    assert '"done":true' in (await anext(stream)).replace(" ", "")
    route.error.assert_not_called()


@pytest.mark.asyncio
async def test_changed_body_never_emits_buffered_quote(route, monkeypatch):
    async def generate(*args, **kwargs):
        yield {"response": "should never escape"}
        yield {"done": True, "done_reason": "stop"}

    monkeypatch.setattr(qa, "stream_verified_quotes", generate)
    route.checked.side_effect = ValueError("version changed")
    events = [event async for event in (await response()).body_iterator]
    assert len(events) == 1 and '"error"' in events[0]
    assert "should never escape" not in events[0]
    route.finish.assert_not_called()
    route.error.assert_called_once()


@pytest.mark.asyncio
async def test_disconnection_closes_generator_and_records_cancellation(route, monkeypatch):
    closed = []

    async def generate(*args, **kwargs):
        try:
            yield {"pending": True}
            pytest.fail("disconnected stream continued")
        finally:
            closed.append(True)

    monkeypatch.setattr(qa, "stream_verified_quotes", generate)
    assert [event async for event in (await response(Request(True))).body_iterator] == []
    assert closed == [True]
    assert route.finish.call_args.kwargs["done_reason"] == "canceled"
    assert route.finish.call_args.kwargs["answer"] == ""


@pytest.mark.asyncio
async def test_task_cancellation_is_recorded_and_propagated(route, monkeypatch):
    async def generate(*args, **kwargs):
        raise asyncio.CancelledError
        yield

    monkeypatch.setattr(qa, "stream_verified_quotes", generate)
    with pytest.raises(asyncio.CancelledError):
        await anext((await response()).body_iterator)
    assert route.finish.call_args.kwargs["done_reason"] == "canceled"
    route.error.assert_not_called()
