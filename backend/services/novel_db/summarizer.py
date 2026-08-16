"""書籍要約・人物生成を調停するapplication service。"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from config import (
    NOVEL_DB_BODY_PAGE_MARGIN,
    NOVEL_DB_LLM_MODEL,
    NOVEL_DB_MIN_BODY_CHARS,
    NOVEL_DB_VERIFIER_MODEL,
)

from .generation_quality import BookFactSheet
from .llm_provider import NovelLlmProvider, get_llm_provider
from .prose_pipeline import (
    extract_fact_sheet,
    write_and_edit_catalog_summary,
    write_and_edit_characters,
    write_and_edit_summary,
)
from .summary_generation import chunk_for_map, run_map_reduce_summary
from .summary_grounding import verify_summary_grounding
from .summary_grounding_parser import SummaryContentType
from .summary_index import index_book_summary
from .summary_prompts import COMBINED_MAX_CHARACTERS
from .summary_repository import (
    get_book_identity,
    load_body_pages,
    load_body_text,
    load_published_character_names,
    load_summaries_for_books,
    update_summary_record,
)

_chunk_for_map = chunk_for_map
_load_body_pages = load_body_pages
_load_body_text = load_body_text
_load_published_character_names = load_published_character_names
_run_map_reduce_summary = run_map_reduce_summary


def summarize_book(
    conn: sqlite3.Connection,
    book_name: str,
    *,
    model: str = NOVEL_DB_LLM_MODEL,
    min_chars: int = NOVEL_DB_MIN_BODY_CHARS,
    body_page_margin: int = NOVEL_DB_BODY_PAGE_MARGIN,
    progress: Callable[[str], None] | None = None,
    provider: NovelLlmProvider | None = None,
) -> str:
    selected_provider = provider or get_llm_provider()
    book_id, page_count = get_book_identity(conn, book_name)
    body_pages = load_body_pages(
        conn,
        book_id,
        page_count,
        min_chars=min_chars,
        body_page_margin=body_page_margin,
    )
    if not body_pages:
        raise ValueError(f"book has no body content: {book_name}")
    fact_sheet = extract_fact_sheet(
        conn,
        book_id,
        book_name,
        body_pages,
        model=model,
        progress=progress,
        canonical_character_names=load_published_character_names(conn, book_id),
        provider=selected_provider,
    )
    summary = write_and_edit_summary(
        book_name,
        fact_sheet,
        model=model,
        progress=progress,
        provider=selected_provider,
    )
    _log(progress, "  verifying summary grounding and fact coverage")
    verify_summary_grounding(
        conn,
        book_id=book_id,
        book_name=book_name,
        summary=summary,
        fact_sheet=fact_sheet,
        writer_model=model,
        verifier_backend=selected_provider.verifier,
        verifier_model=NOVEL_DB_VERIFIER_MODEL or model,
    )
    return summary


def summarize_book_with_characters(
    conn: sqlite3.Connection,
    book_name: str,
    *,
    model: str = NOVEL_DB_LLM_MODEL,
    min_chars: int = NOVEL_DB_MIN_BODY_CHARS,
    body_page_margin: int = NOVEL_DB_BODY_PAGE_MARGIN,
    max_characters: int = COMBINED_MAX_CHARACTERS,
    progress: Callable[[str], None] | None = None,
    provider: NovelLlmProvider | None = None,
) -> tuple[str, str, dict[str, str]]:
    selected_provider = provider or get_llm_provider()
    book_id, page_count = get_book_identity(conn, book_name)
    body_pages = load_body_pages(
        conn,
        book_id,
        page_count,
        min_chars=min_chars,
        body_page_margin=body_page_margin,
    )
    if not body_pages:
        raise ValueError(f"book has no body content: {book_name}")
    fact_sheet = extract_fact_sheet(
        conn,
        book_id,
        book_name,
        body_pages,
        model=model,
        progress=progress,
        canonical_character_names=load_published_character_names(conn, book_id),
        provider=selected_provider,
    )
    summary = write_and_edit_summary(
        book_name=book_name,
        fact_sheet=fact_sheet,
        model=model,
        progress=progress,
        provider=selected_provider,
    )
    _verify(
        conn,
        book_id=book_id,
        book_name=book_name,
        summary=summary,
        fact_sheet=fact_sheet,
        model=model,
        provider=selected_provider,
        content_type="detailed",
        coverage_required=True,
        progress=progress,
    )
    catalog_summary = write_and_edit_catalog_summary(
        book_name,
        fact_sheet,
        summary,
        model=model,
        progress=progress,
        provider=selected_provider,
    )
    _verify(
        conn,
        book_id=book_id,
        book_name=book_name,
        summary=catalog_summary,
        fact_sheet=fact_sheet,
        model=model,
        provider=selected_provider,
        content_type="catalog",
        coverage_required=False,
        progress=progress,
    )
    characters = write_and_edit_characters(
        conn,
        book_id,
        book_name,
        fact_sheet,
        model=model,
        max_characters=max_characters,
        progress=progress,
        provider=selected_provider,
    )
    _log(
        progress,
        f"  done: detailed={len(summary)} chars, catalog={len(catalog_summary)} chars, {len(characters)} characters",
    )
    return summary, catalog_summary, characters


def _verify(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    book_name: str,
    summary: str,
    fact_sheet: BookFactSheet,
    model: str,
    provider: NovelLlmProvider,
    content_type: SummaryContentType,
    coverage_required: bool,
    progress: Callable[[str], None] | None,
) -> None:
    _log(
        progress,
        "  verifying summary grounding and fact coverage"
        if coverage_required
        else "  verifying catalog summary claims",
    )
    verify_summary_grounding(
        conn,
        book_id=book_id,
        book_name=book_name,
        summary=summary,
        fact_sheet=fact_sheet,
        writer_model=model,
        verifier_backend=provider.verifier,
        verifier_model=NOVEL_DB_VERIFIER_MODEL or model,
        content_type=content_type,
        coverage_required=coverage_required,
    )


def update_book_summary(conn: sqlite3.Connection, book_name: str, summary: str) -> None:
    book_id, _ = get_book_identity(conn, book_name)
    update_summary_record(conn, book_id=book_id, summary=summary)
    index_book_summary(conn, book_id, summary)
    conn.commit()


def _log(callback: Callable[[str], None] | None, message: str) -> None:
    if callback is not None:
        callback(message)


__all__ = [
    "index_book_summary",
    "load_summaries_for_books",
    "summarize_book",
    "summarize_book_with_characters",
    "update_book_summary",
]
