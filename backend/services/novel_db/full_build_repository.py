"""本構築の読取りと公開行置換。接続・transactionの確定は呼出し元が所有する。"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from .full_build_content import CharacterRow, GeneratedBookContent


@dataclass(frozen=True)
class PublishedBookState:
    book_id: int
    summary: str | None
    catalog_summary: str | None
    character_names: list[str]
    has_character_summary: bool


def load_published_book_state(conn: sqlite3.Connection, book_name: str) -> PublishedBookState | None:
    row = conn.execute(
        "SELECT id, summary, catalog_summary FROM books WHERE name = ?",
        (book_name,),
    ).fetchone()
    if row is None:
        return None
    book_id, summary, catalog_summary = row
    names = [
        str(character[0])
        for character in conn.execute(
            "SELECT name FROM book_characters WHERE book_id = ? ORDER BY id",
            (book_id,),
        ).fetchall()
    ]
    has_chars = (
        conn.execute(
            "SELECT COUNT(*) FROM book_characters WHERE book_id = ? AND summary IS NOT NULL",
            (book_id,),
        ).fetchone()[0]
        > 0
    )
    return PublishedBookState(book_id, summary, catalog_summary, names, has_chars)


def load_character_evidence_pages(conn: sqlite3.Connection, book_id: int) -> list[tuple[int, str]]:
    rows = conn.execute(
        "SELECT page_no, full_text FROM pages WHERE book_id = ? AND index_eligible = 1 ORDER BY page_no",
        (book_id,),
    ).fetchall()
    return [(int(row[0]), str(row[1] or "")) for row in rows]


def load_character_deletion_texts(conn: sqlite3.Connection, book_id: int) -> list[str]:
    return [
        str(row[0] or "")
        for row in conn.execute(
            "SELECT full_text FROM pages WHERE book_id = ? AND index_eligible = 1",
            (book_id,),
        ).fetchall()
    ]


def replace_published_content(
    conn: sqlite3.Connection,
    book_id: int,
    content: GeneratedBookContent,
    characters: Sequence[CharacterRow],
) -> None:
    """Replace published rows without committing, rolling back, or updating the index."""
    conn.execute(
        """
        UPDATE books
        SET summary = ?,
            summary_generated_at = datetime('now', '+9 hours'),
            catalog_summary = ?,
            catalog_summary_generated_at = datetime('now', '+9 hours')
        WHERE id = ?
        """,
        (content.summary, content.catalog_summary, book_id),
    )
    conn.execute("DELETE FROM book_characters WHERE book_id = ?", (book_id,))
    conn.executemany(
        """INSERT INTO book_characters
               (book_id, name, summary, first_page, page_count, generated_at)
           VALUES (?, ?, ?, ?, ?, datetime('now', '+9 hours'))""",
        [(book_id, *character) for character in characters],
    )
