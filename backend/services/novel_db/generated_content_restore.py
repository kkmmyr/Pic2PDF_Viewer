"""生成内容snapshotのSQLite復元transaction。"""

from __future__ import annotations

import sqlite3

from .generated_content_snapshot import GeneratedContentSnapshot


def restore_generated_content(
    conn: sqlite3.Connection,
    snapshot: GeneratedContentSnapshot,
    *,
    confirmed_book_name: str,
) -> tuple[int, str | None]:
    if confirmed_book_name != snapshot.book_name:
        raise ValueError("confirmed book name does not exactly match the snapshot")
    row = conn.execute("SELECT id FROM books WHERE name = ?", (snapshot.book_name,)).fetchone()
    if row is None:
        raise ValueError(f"book not found: {snapshot.book_name}")
    book_id = int(row["id"])
    try:
        conn.execute("BEGIN IMMEDIATE")
        _restore_book(conn, book_id=book_id, snapshot=snapshot)
        conn.execute("DELETE FROM book_characters WHERE book_id = ?", (book_id,))
        conn.executemany(
            """
            INSERT INTO book_characters
                (book_id, name, summary, first_page, page_count, generated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    book_id,
                    character.name,
                    character.summary,
                    character.first_page,
                    character.page_count,
                    character.generated_at,
                )
                for character in snapshot.characters
            ],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return book_id, snapshot.summary


def _restore_book(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    snapshot: GeneratedContentSnapshot,
) -> None:
    if snapshot.schema_version >= 2:
        conn.execute(
            """
            UPDATE books
            SET summary = ?, summary_generated_at = ?,
                catalog_summary = ?, catalog_summary_generated_at = ?
            WHERE id = ?
            """,
            (
                snapshot.summary,
                snapshot.summary_generated_at,
                snapshot.catalog_summary,
                snapshot.catalog_summary_generated_at,
                book_id,
            ),
        )
    else:
        conn.execute(
            "UPDATE books SET summary = ?, summary_generated_at = ? WHERE id = ?",
            (snapshot.summary, snapshot.summary_generated_at, book_id),
        )
