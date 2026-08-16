"""Novel RAG application serviceのprovider注入境界。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

from local_llm import Backend

from services.novel_db.llm import stream_qa
from services.novel_db.llm_provider import NovelLlmProvider
from services.novel_db.query_expander import expand_query
from services.novel_db.relation_parser import parse_relation_response
from services.novel_db.summary_generation import run_map_reduce_summary


class FakeBackend:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def ask(self, prompt: str, **kwargs: Any) -> str:
        self.calls.append((prompt, kwargs))
        return self.responses.pop(0)

    async def astream_ask(self, prompt: str, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        self.calls.append((prompt, kwargs))
        yield {"response": self.responses.pop(0), "done": False}
        yield {"response": "", "done": True, "eval_count": 1}


def _provider(fake: FakeBackend) -> NovelLlmProvider:
    backend = cast(Backend, fake)
    return NovelLlmProvider(qwen=backend, gemma=backend, query=backend, verifier=backend)


def test_query_expander_accepts_fake_provider_without_global_patch() -> None:
    fake = FakeBackend(["王都 裁判\n主人公 真相"])

    result = expand_query("事件の真相は？", n=3, provider=_provider(fake))

    assert result == ["事件の真相は？", "王都 裁判", "主人公 真相"]
    assert len(fake.calls) == 1


def test_map_reduce_accepts_fake_provider_without_global_patch() -> None:
    fake = FakeBackend(["分割要約", "最終要約"])

    result = run_map_reduce_summary(
        "book",
        "本文",
        model="fake-model",
        provider=_provider(fake),
    )

    assert result == "最終要約"
    assert len(fake.calls) == 2


async def test_stream_qa_accepts_fake_provider_without_global_patch() -> None:
    fake = FakeBackend(["回答"])

    events = [event async for event in stream_qa("質問", provider=_provider(fake))]

    assert events[0]["response"] == "回答"
    assert events[-1]["done"] is True


def test_relation_parser_rejects_non_array_and_normalizes_fenced_json() -> None:
    assert parse_relation_response('{"char_a": "A"}') == []
    assert parse_relation_response('```json\n[{"char_a":"A","char_b":"B","relation":"友人"}]\n```') == [
        ("A", "B", "友人")
    ]
