"""A retry can repair omitted narration without weakening canonical quote checks."""

import json
from types import SimpleNamespace

import pytest

from services.novel_db.qa_grounding import (
    QaSource,
    build_grounded_prompt,
    stream_verified_quotes,
    validate_quote_answer,
)

TEXT = "「お呼びですか」\nそう、俺の専属執事のセバスチャンである。\n「待っていたよ」"
JOINED = "「お呼びですか」「待っていたよ」"


def _answer(quote: str) -> str:
    return json.dumps({"status": "found", "evidence": [{"source_id": 8, "quote": quote}]}, ensure_ascii=False)


def test_quote_that_joins_dialogue_by_omitting_narration_is_rejected():
    sources = [QaSource(8, "テスト冊", 3, TEXT)]
    with pytest.raises(ValueError, match="does not match canonical source"):
        validate_quote_answer(_answer(JOINED), sources)


@pytest.mark.asyncio
async def test_retry_preserves_original_prompt_and_requires_contiguous_quote():
    sources = [QaSource(8, "テスト冊", 3, TEXT)]
    prompt = build_grounded_prompt("二人の会話を示してください。", sources)
    calls = []

    class Backend:
        async def astream_ask(self, received_prompt, **kwargs):
            calls.append((received_prompt, kwargs))
            quote = JOINED if len(calls) == 1 else TEXT
            yield {"response": _answer(quote), "done": False}
            yield {"response": "", "done": True, "done_reason": "stop", "eval_count": 20}

    events = [
        event
        async for event in stream_verified_quotes(
            prompt, sources, model="same-model", options={"temperature": 0.2}, provider=SimpleNamespace(qwen=Backend())
        )
    ]
    assert len(events) == 2
    assert events[0]["response"] == validate_quote_answer(_answer(TEXT), sources)
    assert events[1]["validation_attempts"] == [
        {"attempt": 1, "passed": False, "failure": "quote does not match canonical source"},
        {"attempt": 2, "passed": True},
    ]
    assert calls[0][0] == prompt
    assert calls[1][0].startswith(prompt + "\n\n")
    retry = calls[1][0][len(prompt) :]
    assert "quoteは本文に実在する一つの連続範囲。" in retry
    assert "途中の台詞・地の文・行を省略して連結しない。" in retry
    assert "離れた箇所は別のevidenceとして返す" in retry
    assert "答えを含む短い一つの台詞または一文を優先し、複数の台詞・文が必要なら別々のevidenceに分ける。" in retry
    assert TEXT not in retry and "セバスチャン" not in retry and "source_id8" not in retry
    assert calls[0][1] == calls[1][1]
    assert calls[1][1]["model"] == "same-model"
    assert "format" not in calls[1][1]
