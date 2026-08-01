"""Generated-summary parsing, evidence selection, and deterministic quality gates."""

from __future__ import annotations

import re
from dataclasses import dataclass

_FACT_MARKER_RE = re.compile(r"\[(?:BOOK_FACTS|CHARACTERS?|CHARACTER_FACT:)", re.IGNORECASE)
_PAGE_MARKER_RE = re.compile(r"\[page\s+\d+\]", re.IGNORECASE)
_CHARACTER_FACT_RE = re.compile(
    r"\[CHARACTER_FACT:([^\]]+)\](.*?)(?=\[CHARACTER_FACT:|$)",
    re.DOTALL,
)
_EMPTY_CHARACTER_FACT_RE = re.compile(
    r"^[（(]?\s*(?:該当(?:する)?事実|該当|関連事実|事実|言及|登場)"
    r"(?:は|が)?(?:なし|ない|ありません)(?:[：:。、）)\s]|$)",
)
_SENTENCE_RE = re.compile(r"[^。！？!?\n]+[。！？!?]")
_EDITOR_PREFIX_RE = re.compile(r"^(?:修正版|校正版|編集後|書き直し(?:後)?)[：:\s]")


@dataclass(frozen=True)
class BookFactSheet:
    """Page-grounded facts extracted before prose generation."""

    book_facts: str
    character_facts: dict[str, str]


def parse_fact_sheet(text: str) -> BookFactSheet:
    """Parse marker-based fact extraction output."""
    book_match = re.search(
        r"\[BOOK_FACTS\](.*?)(?=\[CHARACTER_FACT:|$)",
        text,
        re.DOTALL,
    )
    book_facts = book_match.group(1).strip() if book_match else ""
    character_facts: dict[str, str] = {}
    for match in _CHARACTER_FACT_RE.finditer(text):
        name = match.group(1).strip()
        facts = match.group(2).strip()
        if _EMPTY_CHARACTER_FACT_RE.match(facts):
            continue
        if name and facts:
            previous = character_facts.get(name)
            character_facts[name] = f"{previous}\n{facts}" if previous else facts
    return BookFactSheet(book_facts=book_facts, character_facts=character_facts)


def merge_fact_sheets(sheets: list[BookFactSheet]) -> BookFactSheet:
    """Merge chronological fact blocks without discarding repeated character evidence."""
    book_parts = [sheet.book_facts for sheet in sheets if sheet.book_facts]
    character_facts: dict[str, str] = {}
    for sheet in sheets:
        for name, facts in sheet.character_facts.items():
            previous = character_facts.get(name)
            character_facts[name] = f"{previous}\n{facts}" if previous else facts
    return BookFactSheet(
        book_facts="\n\n".join(book_parts),
        character_facts=character_facts,
    )


def format_page_blocks(pages: list[tuple[int, str]]) -> str:
    """Format OCR text with explicit page evidence markers."""
    return "\n\n".join(f"[page {page_no}]\n{text}" for page_no, text in pages)


def chunk_pages_by_chars(
    pages: list[tuple[int, str]],
    *,
    max_chars: int,
) -> list[list[tuple[int, str]]]:
    """Split at page boundaries while preserving every input page."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")

    chunks: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    current_chars = 0
    for page in pages:
        page_chars = len(page[1]) + 32
        if current and current_chars + page_chars > max_chars:
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(page)
        current_chars += page_chars
    if current:
        chunks.append(current)
    return chunks


def select_pages_across_book(
    pages: list[tuple[int, str]],
    *,
    max_chars: int,
    coverage_bins: int = 12,
) -> list[tuple[int, str]]:
    """Fit evidence into a context budget without taking only the beginning.

    The first and final occurrence are considered first. One information-rich
    page per temporal bin follows, then remaining rich pages fill the budget.
    Returned pages stay in reading order.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if not pages:
        return []

    ordered = sorted(pages, key=lambda item: item[0])
    if len(format_page_blocks(ordered)) <= max_chars:
        return ordered

    def block_chars(index: int) -> int:
        page_no, text = ordered[index]
        return len(f"[page {page_no}]\n{text}\n\n")

    mandatory = {0, len(ordered) - 1}
    mandatory_chars = sum(block_chars(index) for index in mandatory)
    if mandatory_chars > max_chars:
        raise ValueError("first and final evidence pages do not fit in the context budget")

    priority: list[int] = []
    bin_count = min(max(1, coverage_bins), len(ordered))
    for bin_index in range(bin_count):
        start = bin_index * len(ordered) // bin_count
        end = (bin_index + 1) * len(ordered) // bin_count
        richest = max(range(start, end), key=lambda idx: len(ordered[idx][1]))
        priority.append(richest)

    selected_seed = set(priority)
    priority.extend(
        sorted(
            (idx for idx in range(len(ordered)) if idx not in selected_seed),
            key=lambda idx: (-len(ordered[idx][1]), ordered[idx][0]),
        )
    )

    selected = set(mandatory)
    used = mandatory_chars
    for index in priority:
        if index in selected:
            continue
        size = block_chars(index)
        if used + size > max_chars:
            continue
        selected.add(index)
        used += size

    return [ordered[index] for index in sorted(selected)]


def generated_prose_issues(
    text: str,
    *,
    required_subject: str | None = None,
) -> list[str]:
    """Return deterministic defects that make generated prose unsafe to publish."""
    value = text.strip()
    issues: list[str] = []
    if not value:
        return ["empty output"]
    if "```" in value:
        issues.append("code fence leaked into prose")
    if _FACT_MARKER_RE.search(value) or "[SUMMARY]" in value:
        issues.append("generation marker leaked into prose")
    if _PAGE_MARKER_RE.search(value):
        issues.append("page marker leaked into prose")
    if _EDITOR_PREFIX_RE.match(value):
        issues.append("editorial label leaked into prose")
    if required_subject and required_subject not in value:
        issues.append(f"subject name is not explicit: {required_subject}")

    paragraphs = [re.sub(r"\s+", " ", part).strip() for part in value.split("\n\n") if part.strip()]
    if len(paragraphs) != len(set(paragraphs)):
        issues.append("duplicate paragraph")

    sentences = [re.sub(r"\s+", "", sentence) for sentence in _SENTENCE_RE.findall(value)]
    meaningful = [sentence for sentence in sentences if len(sentence) >= 12]
    if len(meaningful) != len(set(meaningful)):
        issues.append("duplicate sentence")
    return issues


def choose_publishable_prose(
    draft: str,
    edited: str,
    *,
    required_subject: str | None = None,
) -> str:
    """Prefer the edited candidate, falling back to a valid draft."""
    edited_issues = generated_prose_issues(edited, required_subject=required_subject)
    if not edited_issues:
        return edited.strip()

    draft_issues = generated_prose_issues(draft, required_subject=required_subject)
    if not draft_issues:
        return draft.strip()
    raise ValueError(
        f"no publishable prose candidate: edited={'; '.join(edited_issues)}; draft={'; '.join(draft_issues)}"
    )
