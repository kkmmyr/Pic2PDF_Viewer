"""Fact extraction, separate prose writing, and editorial passes for one novel."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from ._llm_backend import QWEN_BACKEND
from ._prompts import (
    CHARACTER_FACT_EXTRACTION_PROMPT,
    FACT_CHUNK_MAX_CHARS,
    FACT_EXTRACTION_OPTIONS,
    FACT_EXTRACTION_PROMPT,
    ONE_SHOT_OPTIONS,
    PROSE_EDITOR_OPTIONS,
    PROSE_EDITOR_PROMPT,
    SUMMARY_FROM_FACTS_PROMPT,
)
from .character_names import (
    NormalizedCharacter,
    derive_character_evidence_aliases,
    normalize_character_entries,
)
from .character_summarizer import edit_character_summary, summarize_character
from .generation_quality import (
    BookFactSheet,
    choose_publishable_prose,
    chunk_pages_by_chars,
    format_page_blocks,
    merge_fact_sheets,
    parse_fact_sheet,
)

ProgressCallback = Callable[[str], None]


def extract_fact_sheet(
    book_name: str,
    pages: list[tuple[int, str]],
    *,
    model: str,
    progress: ProgressCallback | None,
) -> BookFactSheet:
    """Extract page-grounded book and character facts from every body block."""
    chunks = chunk_pages_by_chars(pages, max_chars=FACT_CHUNK_MAX_CHARS)
    _log(
        progress,
        f"  fact extraction: {len(pages)} pages → {len(chunks)} block(s)",
    )
    sheets: list[BookFactSheet] = []
    for index, chunk in enumerate(chunks, 1):
        prompt = FACT_EXTRACTION_PROMPT.format(
            book_name=book_name,
            part_index=index,
            part_count=len(chunks),
            text=format_page_blocks(chunk),
        )
        book_response = QWEN_BACKEND.ask(
            prompt,
            model=model,
            options=FACT_EXTRACTION_OPTIONS,
        ).strip()
        book_sheet = parse_fact_sheet(book_response)
        if not book_sheet.book_facts:
            raise ValueError(f"fact extraction block {index} did not contain [BOOK_FACTS]")

        character_prompt = CHARACTER_FACT_EXTRACTION_PROMPT.format(
            book_name=book_name,
            book_facts=book_sheet.book_facts,
        )
        character_response = QWEN_BACKEND.ask(
            character_prompt,
            model=model,
            options=FACT_EXTRACTION_OPTIONS,
        ).strip()
        character_sheet = parse_fact_sheet(character_response)
        if not character_sheet.character_facts:
            raise ValueError(f"fact extraction block {index} did not contain named character facts")
        sheet = BookFactSheet(
            book_facts=book_sheet.book_facts,
            character_facts=character_sheet.character_facts,
        )
        sheets.append(sheet)
        _log(
            progress,
            f"  fact block {index}/{len(chunks)}: "
            f"{len(sheet.book_facts)} chars, {len(sheet.character_facts)} characters",
        )

    merged = merge_fact_sheets(sheets)
    if not merged.character_facts:
        raise ValueError("fact extraction did not contain any named character facts")
    return merged


def write_and_edit_summary(
    book_name: str,
    fact_sheet: BookFactSheet,
    *,
    model: str,
    progress: ProgressCallback | None,
) -> str:
    """Write a book summary from facts, then run a separate editorial pass."""
    facts = _render_fact_sheet(fact_sheet)
    _log(progress, "  writing book summary from facts")
    draft_prompt = SUMMARY_FROM_FACTS_PROMPT.format(
        book_name=book_name,
        facts=facts,
    )
    draft = QWEN_BACKEND.ask(
        draft_prompt,
        model=model,
        options=ONE_SHOT_OPTIONS,
    ).strip()

    _log(progress, "  editing book summary")
    editor_prompt = PROSE_EDITOR_PROMPT.format(
        book_name=book_name,
        document_type="あらすじ・要約",
        facts=facts,
        draft=draft,
    )
    edited = QWEN_BACKEND.ask(
        editor_prompt,
        model=model,
        options=PROSE_EDITOR_OPTIONS,
    ).strip()
    return choose_publishable_prose(draft, edited)


def write_and_edit_characters(
    conn: sqlite3.Connection,
    book_id: int,
    book_name: str,
    fact_sheet: BookFactSheet,
    *,
    model: str,
    max_characters: int,
    progress: ProgressCallback | None,
) -> dict[str, str]:
    """Write and edit each evidenced character independently."""
    page_rows = [
        (int(page_no), str(text))
        for page_no, text in conn.execute(
            """
            SELECT page_no, full_text
            FROM pages
            WHERE book_id = ? AND index_eligible = 1
              AND full_text IS NOT NULL AND full_text <> ''
            ORDER BY page_no
            """,
            (book_id,),
        ).fetchall()
    ]

    candidates: list[tuple[NormalizedCharacter, list[tuple[int, str]]]] = []
    for entry in normalize_character_entries(fact_sheet.character_facts):
        evidence_pages = _find_character_evidence_pages(entry, page_rows)
        if evidence_pages:
            candidates.append((entry, evidence_pages))
        else:
            _log(progress, f"  omit character without page evidence: {entry.name}")

    candidates.sort(
        key=lambda item: (
            -len(item[1]),
            item[1][0][0],
            item[0].name,
        )
    )
    candidates = candidates[:max_characters]
    if not candidates:
        raise ValueError("no character facts had matching page evidence")

    result: dict[str, str] = {}
    for index, (entry, evidence_pages) in enumerate(candidates, 1):
        _log(
            progress,
            f"  character {index}/{len(candidates)}: {entry.name} ({len(evidence_pages)} evidence pages)",
        )
        draft = summarize_character(
            book_name,
            entry.name,
            evidence_pages,
            model=model,
            fact_notes=entry.summary,
            progress=progress,
        )
        edited = edit_character_summary(
            book_name,
            entry.name,
            draft,
            fact_notes=entry.summary,
            model=model,
        )
        result[entry.name] = choose_publishable_prose(
            draft,
            edited,
            required_subject=entry.name,
        )
    return result


def _render_fact_sheet(fact_sheet: BookFactSheet) -> str:
    parts = [f"[BOOK_FACTS]\n{fact_sheet.book_facts}"]
    parts.extend(f"[CHARACTER_FACT:{name}]\n{facts}" for name, facts in fact_sheet.character_facts.items())
    return "\n\n".join(parts)


def _find_character_evidence_pages(
    entry: NormalizedCharacter,
    page_rows: list[tuple[int, str]],
) -> list[tuple[int, str]]:
    derived_aliases = derive_character_evidence_aliases(entry.name)
    derived_counts = {alias: sum(alias in text for _, text in page_rows) for alias in derived_aliases}
    aliases = (
        *entry.aliases,
        *(alias for alias, count in derived_counts.items() if count >= 2),
    )
    return [(page_no, text) for page_no, text in page_rows if any(alias in text for alias in aliases)]


def _log(cb: ProgressCallback | None, msg: str) -> None:
    if cb is not None:
        cb(msg)
