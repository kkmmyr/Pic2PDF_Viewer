"""書籍要約のmap-reduce生成と分割を担うdomain service。"""

from __future__ import annotations

from collections.abc import Callable

from .llm_provider import NovelLlmProvider, get_llm_provider
from .summary_prompts import (
    MAP_CHUNK_TARGET_CHARS,
    MAP_MAX_CHUNKS,
    MAP_OPTIONS,
    MAP_PROMPT,
    REDUCE_OPTIONS,
    REDUCE_PROMPT,
)


def chunk_for_map(text: str) -> list[str]:
    if len(text) <= MAP_CHUNK_TARGET_CHARS:
        return [text]
    chunk_count = min(
        MAP_MAX_CHUNKS,
        (len(text) + MAP_CHUNK_TARGET_CHARS - 1) // MAP_CHUNK_TARGET_CHARS,
    )
    target = len(text) // chunk_count
    chunks: list[str] = []
    cursor = 0
    for _ in range(chunk_count - 1):
        newline = text.find("\n", cursor + target)
        if newline == -1 or newline >= len(text) - 1:
            chunks.append(text[cursor:])
            return chunks
        chunks.append(text[cursor:newline])
        cursor = newline + 1
    chunks.append(text[cursor:])
    return chunks


def run_map_reduce_summary(
    book_name: str,
    body_text: str,
    *,
    model: str,
    progress: Callable[[str], None] | None = None,
    provider: NovelLlmProvider | None = None,
) -> str:
    backend = (provider or get_llm_provider()).qwen
    chunks = chunk_for_map(body_text)
    _log(progress, f"  body chars={len(body_text):,} → map-reduce ({len(chunks)} chunks, 超過のため)")
    intermediates: list[str] = []
    for index, chunk in enumerate(chunks, 1):
        _log(progress, f"  map {index}/{len(chunks)} (chars={len(chunk):,})...")
        prompt = MAP_PROMPT.format(
            book_name=book_name,
            i=index,
            n=len(chunks),
            text=chunk,
        )
        intermediates.append(backend.ask(prompt, model=model, options=MAP_OPTIONS).strip())
    _log(progress, f"  reduce ({sum(len(value) for value in intermediates):,} chars)...")
    summaries = "\n\n".join(f"[{index}/{len(intermediates)}]\n{value}" for index, value in enumerate(intermediates, 1))
    return backend.ask(
        REDUCE_PROMPT.format(book_name=book_name, summaries=summaries),
        model=model,
        options=REDUCE_OPTIONS,
    ).strip()


def _log(callback: Callable[[str], None] | None, message: str) -> None:
    if callback is not None:
        callback(message)
