"""書籍要約applicationが使用するSQLite read/write repository。"""

from __future__ import annotations

import sqlite3


def get_book_identity(conn: sqlite3.Connection, book_name: str) -> tuple[int, int]:
    row = conn.execute(
        "SELECT id, page_count FROM books WHERE name = ?",
        (book_name,),
    ).fetchone()
    if row is None:
        raise ValueError(f"book not found: {book_name}")
    return int(row[0]), int(row[1])


def load_published_character_names(conn: sqlite3.Connection, book_id: int) -> list[str]:
    return [
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM book_characters WHERE book_id = ? ORDER BY id",
            (book_id,),
        ).fetchall()
    ]


def load_body_pages(
    conn: sqlite3.Connection,
    book_id: int,
    page_count: int,
    *,
    min_chars: int,
    body_page_margin: int,
) -> list[tuple[int, str]]:
    rows = conn.execute(
        """
        SELECT page_no, full_text
        FROM pages
        WHERE book_id = ?
          AND index_eligible = 1
          AND char_count >= ?
          AND page_no > ?
          AND page_no <= ?
        ORDER BY page_no
        """,
        (book_id, min_chars, body_page_margin, page_count - body_page_margin),
    ).fetchall()
    return [(int(page_no), str(text)) for page_no, text in rows if text]


def load_body_text(
    conn: sqlite3.Connection,
    book_id: int,
    page_count: int,
    *,
    min_chars: int,
    body_page_margin: int,
) -> str:
    pages = load_body_pages(
        conn,
        book_id,
        page_count,
        min_chars=min_chars,
        body_page_margin=body_page_margin,
    )
    return "\n".join(text for _, text in pages)


def update_summary_record(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    summary: str,
) -> None:
    conn.execute(
        "UPDATE books SET summary = ?, summary_generated_at = datetime('now', '+9 hours') WHERE id = ?",
        (summary, book_id),
    )


def load_summaries_for_books(
    conn: sqlite3.Connection,
    book_names: list[str],
) -> dict[str, str]:
    if not book_names:
        return {}
    placeholders = ",".join("?" * len(book_names))
    rows = conn.execute(
        f"SELECT name, summary FROM books WHERE name IN ({placeholders}) AND summary IS NOT NULL AND summary <> ''",
        book_names,
    ).fetchall()
    return {str(name): str(summary) for name, summary in rows}
