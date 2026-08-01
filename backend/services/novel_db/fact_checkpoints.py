"""Validated, reusable checkpoints for page-grounded fact extraction."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from typing import TypedDict

from .generation_quality import BookFactSheet

FACT_EXTRACTION_SCHEMA_VERSION = 3

_PAGE_GROUP_RE = re.compile(
    r"\[\s*page\s+\d+(?:\s*[,、/&・]\s*(?:page\s+)?\d+)*\s*\]",
    re.IGNORECASE,
)
_PAGE_NUMBER_RE = re.compile(r"\d+")
_BULLET_RE = re.compile(r"^(?:[-*・]\s*)")


class FactRecordPayload(TypedDict):
    kind: str
    character_name: str | None
    pages: list[int]
    text: str


@dataclass(frozen=True)
class FactRecord:
    """One atomic fact and the source pages claimed by the extractor."""

    kind: str
    character_name: str | None
    pages: tuple[int, ...]
    text: str

    def to_payload(self) -> FactRecordPayload:
        return {
            "kind": self.kind,
            "character_name": self.character_name,
            "pages": list(self.pages),
            "text": self.text,
        }


def hash_source_pages(
    pages: list[tuple[int, str]],
    *,
    prompt_context: str = "",
) -> str:
    """Return a stable hash for an ordered page block and prompt context."""
    digest = hashlib.sha256()
    digest.update(prompt_context.encode("utf-8"))
    digest.update(b"\x1d")
    for page_no, text in pages:
        digest.update(str(page_no).encode("ascii"))
        digest.update(b"\x1f")
        digest.update(text.encode("utf-8"))
        digest.update(b"\x1e")
    return digest.hexdigest()


def validate_and_structure_fact_sheet(
    sheet: BookFactSheet,
    *,
    allowed_pages: set[int],
) -> list[FactRecord]:
    """Parse every fact into records and reject missing or invented page evidence."""
    records = _parse_fact_lines(sheet.book_facts, kind="book", character_name=None)
    for name, facts in sheet.character_facts.items():
        records.extend(_parse_fact_lines(facts, kind="character", character_name=name))

    if not records:
        raise ValueError("fact extraction did not contain structured facts")
    for record in records:
        invalid_pages = sorted(set(record.pages) - allowed_pages)
        if invalid_pages:
            raise ValueError(
                "fact extraction referenced pages outside its block: " + ", ".join(str(page) for page in invalid_pages)
            )
    return records


def load_fact_block(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    block_index: int,
    source_hash: str,
    model: str,
) -> BookFactSheet | None:
    """Load a checkpoint only when all cache identity fields match."""
    row = conn.execute(
        """
        SELECT book_facts, character_facts_json, fact_records_json
        FROM fact_extraction_blocks
        WHERE book_id = ? AND block_index = ? AND source_hash = ?
          AND model = ? AND schema_version = ?
        """,
        (
            book_id,
            block_index,
            source_hash,
            model,
            FACT_EXTRACTION_SCHEMA_VERSION,
        ),
    ).fetchone()
    if row is None:
        return None

    try:
        character_facts = json.loads(str(row[1]))
        records = json.loads(str(row[2]))
    except json.JSONDecodeError:
        return None
    if not isinstance(character_facts, dict) or not all(
        isinstance(name, str) and isinstance(facts, str) for name, facts in character_facts.items()
    ):
        return None
    if not isinstance(records, list) or not records:
        return None
    return BookFactSheet(
        book_facts=str(row[0]),
        character_facts=character_facts,
    )


def save_fact_block(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    block_index: int,
    pages: list[tuple[int, str]],
    source_hash: str,
    model: str,
    sheet: BookFactSheet,
    records: list[FactRecord],
) -> None:
    """Persist one completed block independently from later prose publication."""
    conn.execute(
        """
        INSERT INTO fact_extraction_blocks
            (book_id, block_index, page_start, page_end, source_hash, model,
             schema_version, book_facts, character_facts_json, fact_records_json,
             generated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', '+9 hours'))
        ON CONFLICT(book_id, block_index) DO UPDATE SET
            page_start = excluded.page_start,
            page_end = excluded.page_end,
            source_hash = excluded.source_hash,
            model = excluded.model,
            schema_version = excluded.schema_version,
            book_facts = excluded.book_facts,
            character_facts_json = excluded.character_facts_json,
            fact_records_json = excluded.fact_records_json,
            generated_at = excluded.generated_at
        """,
        (
            book_id,
            block_index,
            pages[0][0],
            pages[-1][0],
            source_hash,
            model,
            FACT_EXTRACTION_SCHEMA_VERSION,
            sheet.book_facts,
            json.dumps(sheet.character_facts, ensure_ascii=False, sort_keys=True),
            json.dumps(
                [record.to_payload() for record in records],
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
    )
    conn.commit()


def prune_fact_blocks(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    block_count: int,
) -> None:
    """Remove obsolete tail blocks after a book becomes shorter or chunking changes."""
    conn.execute(
        "DELETE FROM fact_extraction_blocks WHERE book_id = ? AND block_index > ?",
        (book_id, block_count),
    )
    conn.commit()


def _parse_fact_lines(
    value: str,
    *,
    kind: str,
    character_name: str | None,
) -> list[FactRecord]:
    items: list[str] = []
    current: list[str] = []
    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _BULLET_RE.match(line):
            if current:
                items.append(" ".join(current))
            current = [_BULLET_RE.sub("", line, count=1).strip()]
        elif current:
            current.append(line)
        else:
            current = [line]
    if current:
        items.append(" ".join(current))

    records: list[FactRecord] = []
    for item in items:
        page_groups = _PAGE_GROUP_RE.findall(item)
        pages = tuple(dict.fromkeys(int(page) for group in page_groups for page in _PAGE_NUMBER_RE.findall(group)))
        if not pages:
            label = character_name or kind
            raise ValueError(f"fact is missing page evidence ({label}): {item[:80]}")
        text = re.sub(r"\s+", " ", _PAGE_GROUP_RE.sub("", item)).strip(" -・*\t")
        if not text:
            raise ValueError("fact text is empty after removing page evidence")
        records.append(
            FactRecord(
                kind=kind,
                character_name=character_name,
                pages=pages,
                text=text,
            )
        )
    return records
