"""No generated text reaches clients before canonical quote validation."""

import asyncio
import json
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest
from local_llm import LLMError

from services.novel_db import qa_grounding as grounding


@pytest.fixture
def sources():
    return [
        grounding.QaSource(0, "本A", 7, "前置き。答えは\n　青い石。後書き。"),
        grounding.QaSource(1, "本B", 9, "別の根拠。"),
    ]


def raw(quote="答えは青い石。", source_id=0):
    return json.dumps({"status": "found", "evidence": [{"source_id": source_id, "quote": quote}]}, ensure_ascii=False)


def provider(events):
    calls = []

    async def ask(prompt, **kwargs):
        calls.append((prompt, kwargs))
        for event in events:
            yield event

    return SimpleNamespace(qwen=SimpleNamespace(astream_ask=ask)), calls


async def consume(sources, events, **kwargs):
    backend, calls = provider(events)
    result = [
        event
        async for event in grounding.stream_verified_quotes(
            "prompt", sources, model="fixed-model", options={"presence_penalty": 0.0}, provider=backend, **kwargs
        )
    ]
    return result, calls


def test_prompt_serialization_and_frozen_sources(sources):
    prompt = grounding.build_grounded_prompt("質問？", sources)
    encoded = '[{"source_id": 0, "book_name": "本A", "page_no": 7, "text": "前置き。答えは\\n　青い石。後書き。"}, {"source_id": 1, "book_name": "本B", "page_no": 9, "text": "別の根拠。"}]'
    assert "【参照本文】\n" + encoded + "\n\n【質問】\n質問？" in prompt
    assert prompt.endswith("この質問の具体的な答えを含む原文の引用を選び、指定されたJSON objectだけを返してください。")
    with pytest.raises(FrozenInstanceError):
        sources[0].page_no = 99


def test_whitespace_normalization_restores_canonical_quote_and_metadata(sources):
    answer = grounding.validate_quote_answer(raw(), sources)
    assert "本A／page 7" in answer
    assert "> 前置き。答えは\n> 　青い石。後書き。" in answer


@pytest.mark.parametrize(
    ("text", "quote", "expected"),
    [
        (
            "さらに前\n【トリィティ】\n光を放つ魔法。\n次の文脈\nさらに後",
            "光を放つ魔法。",
            "【トリィティ】\n光を放つ魔法。\n次の文脈",
        ),
        ("前行\n左側。選択本文。右側\n後行\n除外", "選択本文。", "前行\n左側。選択本文。右側\n後行"),
        ("選択本文。\n後行\n除外", "選択本文。", "選択本文。\n後行"),
        ("除外\n前行\n選択本文。", "選択本文。", "前行\n選択本文。"),
        ("あ" * 600 + "選択本文。" + "い" * 600, "選択本文。", "あ" * 500 + "選択本文。" + "い" * 500),
    ],
)
def test_quote_context_is_exact_bounded_canonical_slice(text, quote, expected):
    source = grounding.QaSource(0, "本", 1, text)
    result = grounding.validate_quote_answer(raw(quote), [source])
    assert result == "根拠（本／page 1）：\n\n" + "\n".join("> " + line for line in expected.split("\n"))


def test_mismatch_rejected_before_context_and_ambiguous_position_rejected():
    source = grounding.QaSource(0, "本", 1, "名前\n本文。\n本文。")
    with pytest.raises(ValueError, match="does not match"):
        grounding.validate_quote_answer(raw("架空の本文。"), [source])
    with pytest.raises(ValueError, match="ambiguous"):
        grounding.validate_quote_answer(raw("本文。"), [source])


def test_not_found_is_explicit(sources):
    assert (
        grounding.validate_quote_answer('{"status":"not_found","evidence":[]}', sources)
        == "取得した本文内では該当箇所が見つかりません。"
    )


@pytest.mark.parametrize(
    "bad",
    [
        '{"status":"found","status":"found","evidence":[]}',
        '{"status":"found","evidence":[{"source_id":0,"source_id":1,"quote":"別の根拠。"}]}',
        '{"status":NaN,"evidence":[]}',
        '{"status":"found","evidence":[{"source_id":Infinity,"quote":"a"}]}',
        "[]",
        '{"status":"found","evidence":[],"answer":"extra"}',
        '{"status":"found","evidence":[]}',
        '{"status":"not_found","evidence":[{"source_id":0,"quote":"答え"}]}',
        '{"status":"invalid","evidence":[]}',
        '{"status":"found","evidence":[{"source_id":true,"quote":"答え"}]}',
        '{"status":"found","evidence":[{"source_id":0.0,"quote":"答え"}]}',
        '{"status":"found","evidence":[{"source_id":99,"quote":"答え"}]}',
        '{"status":"found","evidence":[{"source_id":0,"quote":"答え","page_no":7}]}',
        raw(""),
        raw(" \n　"),
        raw("a" * 501),
        raw("存在しない原文"),
        raw("答えは青い石。", 1),
        raw("答えは…青い石。"),
        json.dumps({"status": "found", "evidence": [{"source_id": 0, "quote": "答え"}] * 5}),
        json.dumps(
            {
                "status": "found",
                "evidence": [
                    {"source_id": 0, "quote": "答えは青い石。"},
                    {"source_id": 0, "quote": "答えは\n　青い石。"},
                ],
            }
        ),
        '{"status":"found","evidence":"wrong"}',
        '```json\n{"status":"not_found","evidence":[]}\n```',
    ],
)
def test_invalid_or_generated_metadata_fails_closed(sources, bad):
    with pytest.raises(ValueError):
        grounding.validate_quote_answer(bad, sources)


def test_duplicate_source_id_rejected(sources):
    with pytest.raises(ValueError, match="duplicate source ID"):
        grounding.build_grounded_prompt("question", [sources[0], sources[0]])


async def test_buffers_response_and_preserves_success_metadata(sources):
    text = raw()
    result, calls = await consume(
        sources,
        [
            {"response": text[:10], "done": False},
            {"response": text[10:], "done": False},
            {"response": "", "done": True, "done_reason": "stop", "eval_count": 42},
        ],
    )
    assert len(result) == 2
    assert result[0]["response"] == grounding.validate_quote_answer(text, sources)
    assert result[1]["eval_count"] == 42
    assert result[1]["validation_attempts"] == [{"attempt": 1, "passed": True}]
    assert calls[0][1]["think"] is False
    assert "format" not in calls[0][1]
    assert calls[0][1]["options"] == {"presence_penalty": 0.0}


@pytest.mark.parametrize(
    "events",
    [
        [{"response": raw(), "done": False}],
        [{"response": raw(), "done": True, "done_reason": "length"}],
        [{"response": raw(), "done": True, "done_reason": "stop"}, {"response": "after"}],
        [{"response": raw(), "done": True, "done_reason": "stop"}, {"done": True, "done_reason": "stop"}],
        [{"response": "x" * 12001}],
        [{"response": 17}],
    ],
)
async def test_transport_failures_never_yield_unverified_answer_or_retry(sources, events):
    backend, calls = provider(events)
    seen = []
    with pytest.raises(LLMError):
        async for event in grounding.stream_verified_quotes("prompt", sources, model="m", options={}, provider=backend):
            seen.append(event)
    assert seen == []
    assert len(calls) == 1


@pytest.mark.parametrize("succeeds", [True, False])
async def test_invalid_quote_retries_same_source_and_model_only(sources, succeeds):
    calls = []
    invalid = raw("answer invented", 1)

    async def ask(prompt, **kwargs):
        calls.append((prompt, kwargs))
        yield {"response": raw() if len(calls) == 2 and succeeds else invalid}
        yield {"done": True, "done_reason": "stop", "eval_count": 8}

    backend = SimpleNamespace(qwen=SimpleNamespace(astream_ask=ask))
    stream = grounding.stream_verified_quotes(
        "fixed prompt", sources, model="same-model", options={"temperature": 0.2}, provider=backend
    )
    if succeeds:
        result = [event async for event in stream]
        attempts = result[-1]["validation_attempts"]
        assert [a["passed"] for a in attempts] == [False, True]
        assert "quote does not match canonical source" in attempts[0]["failure"]
    else:
        seen = []
        with pytest.raises(LLMError, match="two attempts"):
            async for event in stream:
                seen.append(event)
        assert seen == []
    assert len(calls) == 2
    assert calls[0][0] == "fixed prompt"
    assert calls[1][0].startswith("fixed prompt\n\n前の出力")
    assert "青い石" not in calls[1][0]
    assert all(c[1]["model"] == "same-model" for c in calls)


async def test_pending_only_then_disconnect_cancels_background_generation(sources, monkeypatch):
    monkeypatch.setattr(grounding, "PENDING_INTERVAL", 0.005)
    stopped = asyncio.Event()

    async def ask(prompt, **kwargs):
        try:
            await asyncio.Event().wait()
            yield {"response": "unreachable"}
        finally:
            stopped.set()

    backend = SimpleNamespace(qwen=SimpleNamespace(astream_ask=ask))
    stream = grounding.stream_verified_quotes("prompt", sources, model="m", options={}, provider=backend)
    assert await anext(stream) == {"pending": True}
    assert not stopped.is_set()
    await stream.aclose()
    assert stopped.is_set()


async def test_wall_timeout_cancels_backend_and_does_not_retry(sources):
    calls = []
    stopped = asyncio.Event()

    async def ask(prompt, **kwargs):
        calls.append(prompt)
        try:
            await asyncio.Event().wait()
            yield {"response": "unreachable"}
        finally:
            stopped.set()

    backend = SimpleNamespace(qwen=SimpleNamespace(astream_ask=ask))
    with pytest.raises(TimeoutError):
        async for _ in grounding.stream_verified_quotes(
            "prompt", sources, model="m", options={}, provider=backend, timeout=0.01
        ):
            pytest.fail("unexpected output")
    assert stopped.is_set()
    assert len(calls) == 1


async def test_external_task_cancellation_closes_backend(sources):
    stopped = asyncio.Event()
    entered = asyncio.Event()

    async def ask(prompt, **kwargs):
        try:
            entered.set()
            await asyncio.Event().wait()
            yield {"response": "unreachable"}
        finally:
            stopped.set()

    backend = SimpleNamespace(qwen=SimpleNamespace(astream_ask=ask))
    stream = grounding.stream_verified_quotes("prompt", sources, model="m", options={}, provider=backend)
    task = asyncio.create_task(anext(stream))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()


async def test_retries_share_single_wall_timeout(sources, monkeypatch):
    original_timeout = asyncio.timeout
    timeouts = []
    calls = []
    closed = asyncio.Event()

    def counted_timeout(delay):
        timeouts.append(delay)
        return original_timeout(delay)

    async def ask(prompt, **kwargs):
        calls.append(prompt)
        if len(calls) == 1:
            yield {"response": raw("wrong source")}
            yield {"done": True, "done_reason": "stop"}
        else:
            try:
                await asyncio.Event().wait()
                yield {"response": "unreachable"}
            finally:
                closed.set()

    monkeypatch.setattr(grounding.asyncio, "timeout", counted_timeout)
    backend = SimpleNamespace(qwen=SimpleNamespace(astream_ask=ask))
    with pytest.raises(TimeoutError):
        async for _ in grounding.stream_verified_quotes(
            "prompt", sources, model="m", options={}, provider=backend, timeout=0.02
        ):
            pytest.fail("unverified answer escaped")
    assert len(calls) == 2
    assert closed.is_set()
    assert timeouts == [0.02]
