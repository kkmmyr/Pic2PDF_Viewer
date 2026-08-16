"""読書会plan生成とstream変換を調停するapplication service。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

from config import KINDLE_NOVEL_DIR, NOVEL_DB_LLM_MODEL, NOVEL_DB_QA_FULL_BOOK_NUM_CTX
from utils.logger import get_logger

from .discussion_parser import extract_plan_json, parse_turns_from_text, validate_plan
from .discussion_repository import (
    count_discussions as count_discussions_from,
)
from .discussion_repository import (
    delete_discussion as delete_discussion_from,
)
from .discussion_repository import (
    discussion_book_dir,
)
from .discussion_repository import (
    list_discussions as list_discussions_from,
)
from .discussion_repository import (
    save_discussion as save_discussion_to,
)
from .discussion_stream import stream_discussion_events
from .llm import astream_chat as _astream_chat
from .llm_options import make_llm_options
from .llm_provider import NovelLlmProvider
from .search import SearchHit

logger = get_logger(__name__)
DISCUSSIONS_DIR = Path(KINDLE_NOVEL_DIR) / "discussions"
_CHARS_PER_TOKEN = 1.5
MAX_INPUT_TOKENS = 112_000
_PLAN_MAX_ATTEMPTS = 3

LLM_OPTIONS = make_llm_options(
    temperature=0.7,
    repeat_penalty=1.1,
    num_predict=8192,
    num_ctx=NOVEL_DB_QA_FULL_BOOK_NUM_CTX,
)
PLAN_LLM_OPTIONS = make_llm_options(
    temperature=0.4,
    repeat_penalty=1.1,
    num_predict=2048,
    num_ctx=NOVEL_DB_QA_FULL_BOOK_NUM_CTX,
)

_parse_turns_from_text = parse_turns_from_text
_extract_json_object = extract_plan_json
_validate_plan = validate_plan


def estimate_book_tokens(hits: list[SearchHit]) -> int:
    return int(sum(len(hit.snippet) for hit in hits) / _CHARS_PER_TOKEN)


def format_book_text(hits: list[SearchHit]) -> str:
    return "\n\n".join(f"[page {hit.page_no}]\n{hit.snippet}" for hit in hits)


async def generate_plan(
    messages: list[dict],
    *,
    model: str = NOVEL_DB_LLM_MODEL,
    options: dict | None = None,
    provider: NovelLlmProvider | None = None,
) -> dict:
    selected_options = options or PLAN_LLM_OPTIONS
    last_error: ValueError | None = None
    for attempt in range(1, _PLAN_MAX_ATTEMPTS + 1):
        text = await _collect_response(
            messages,
            model=model,
            options=selected_options,
            provider=provider,
        )
        try:
            plan = extract_plan_json(text)
            validate_plan(plan)
            return plan
        except json.JSONDecodeError as exc:
            last_error = ValueError(f"構成メモの JSON パースに失敗しました: {exc}")
            last_error.__cause__ = exc
        except ValueError as exc:
            last_error = exc
        logger.warning(
            "generate_plan attempt %d/%d failed: %s",
            attempt,
            _PLAN_MAX_ATTEMPTS,
            last_error,
        )
    if last_error is None:
        raise RuntimeError("generate_plan failed without validation error")
    raise last_error


async def stream_discussion_turns(
    messages: list[dict],
    *,
    model: str = NOVEL_DB_LLM_MODEL,
    options: dict | None = None,
    provider: NovelLlmProvider | None = None,
) -> AsyncIterator[dict]:
    async def chat_stream(*args, **kwargs):
        if provider is not None:
            kwargs["provider"] = provider
        async for event in _astream_chat(*args, **kwargs):
            yield event

    async for event in stream_discussion_events(
        messages,
        chat_stream=chat_stream,
        model=model,
        options=options or LLM_OPTIONS,
    ):
        yield event


async def _collect_response(
    messages: list[dict],
    *,
    model: str,
    options: dict,
    provider: NovelLlmProvider | None,
) -> str:
    chunks: list[str] = []
    kwargs = {"model": model, "options": options}
    if provider is not None:
        kwargs["provider"] = provider
    async for event in _astream_chat(messages, **kwargs):
        response = event.get("response")
        if isinstance(response, str) and response:
            chunks.append(response)
        if event.get("done"):
            break
    return "".join(chunks)


def _discussion_book_dir(book_name: str) -> Path:
    return discussion_book_dir(DISCUSSIONS_DIR, book_name)


def save_discussion(
    book_name: str,
    cast_snapshot: list[dict],
    segments: list[dict],
    cards: list[dict],
    turns: list[dict],
    checks: dict,
) -> str:
    return save_discussion_to(
        DISCUSSIONS_DIR,
        book_name,
        cast_snapshot,
        segments,
        cards,
        turns,
        checks,
    )


def count_discussions(book_name: str) -> int:
    return count_discussions_from(DISCUSSIONS_DIR, book_name)


def list_discussions(book_name: str) -> list[dict]:
    return list_discussions_from(DISCUSSIONS_DIR, book_name)


def delete_discussion(book_name: str, filename: str) -> bool:
    return delete_discussion_from(DISCUSSIONS_DIR, book_name, filename)
