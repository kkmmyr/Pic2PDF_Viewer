"""書籍要約のLanceDB index更新境界。"""

from __future__ import annotations

import logging
import sqlite3

from .embedder import embed_batch
from .lance_store import get_summaries_table

logger = logging.getLogger(__name__)


def index_book_summary(
    conn: sqlite3.Connection,
    book_id: int,
    summary: str,
    *,
    raise_on_error: bool = False,
) -> None:
    try:
        embedding = embed_batch([summary])[0]
        row = conn.execute("SELECT name FROM books WHERE id = ?", (book_id,)).fetchone()
        book_name = str(row[0]) if row else ""
        table = get_summaries_table()
        table.delete(f"book_id = {book_id}")
        table.add([{"book_id": book_id, "book_name": book_name, "embedding": embedding}])
    except Exception as exc:
        logger.warning("Failed to index summary vector for book_id=%s: %s", book_id, exc)
        if raise_on_error:
            raise
