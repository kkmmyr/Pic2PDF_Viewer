"""補正済み1ページの検索索引を安全に再構築する。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from lancedb.table import Table

from utils.logger import get_logger

from .chunker import MIN_CHARS_FOR_CHUNK, chunk_page
from .embedder import embed_batch
from .lance_store import get_chunks_table
from .page_fts import mark_page_fts_stale

logger = get_logger(__name__)

_LANCE_COLUMNS = [
    "chunk_id",
    "book_name",
    "page_no",
    "text",
    "char_count",
    "page_count",
    "embedding",
]


@dataclass(frozen=True)
class _PageContext:
    book_id: int
    book_name: str
    page_count: int
    page_id: int
    page_no: int
    full_text: str
    char_count: int
    index_eligible: bool


def _chunk_id_filter(chunk_ids: list[int]) -> str:
    return f"chunk_id IN ({', '.join(str(chunk_id) for chunk_id in chunk_ids)})"


def _load_page_context(
    conn: sqlite3.Connection,
    book_name: str,
    page_no: int,
) -> _PageContext:
    book_row = conn.execute(
        "SELECT id, name, page_count FROM books WHERE name = ?",
        (book_name,),
    ).fetchone()
    if book_row is None:
        raise ValueError(f"book not found (run OCR first): {book_name}")

    book_id = int(book_row[0])
    page_row = conn.execute(
        "SELECT id, full_text, char_count, index_eligible FROM pages WHERE book_id = ? AND page_no = ?",
        (book_id, page_no),
    ).fetchone()
    if page_row is None:
        raise ValueError(f"page not found: {book_name} p{page_no}")

    return _PageContext(
        book_id=book_id,
        book_name=str(book_row[1]),
        page_count=int(book_row[2] or 0),
        page_id=int(page_row[0]),
        page_no=page_no,
        full_text=str(page_row[1] or ""),
        char_count=int(page_row[2] or 0),
        index_eligible=bool(page_row[3]),
    )


def _prepare_chunks(context: _PageContext) -> tuple[list[str], list[list[float]]]:
    if not context.index_eligible or context.char_count < MIN_CHARS_FOR_CHUNK:
        return [], []
    texts = chunk_page(context.full_text)
    return texts, embed_batch(texts)


def _snapshot_lance_rows(table: Table, chunk_ids: list[int]) -> list[dict[str, object]]:
    if not chunk_ids:
        return []
    return table.search().where(_chunk_id_filter(chunk_ids)).select(_LANCE_COLUMNS).limit(len(chunk_ids)).to_list()


def _insert_new_chunks(
    conn: sqlite3.Connection,
    context: _PageContext,
    texts: list[str],
    embeddings: list[list[float]],
) -> tuple[list[int], list[dict[str, object]]]:
    chunk_ids: list[int] = []
    lance_rows: list[dict[str, object]] = []
    for chunk_idx, (text, embedding) in enumerate(zip(texts, embeddings, strict=True)):
        cursor = conn.execute(
            "INSERT INTO chunks (page_id, chunk_idx, text, char_count) VALUES (?, ?, ?, ?)",
            (context.page_id, chunk_idx, text, len(text)),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("failed to allocate chunk id")
        chunk_id = cursor.lastrowid
        chunk_ids.append(chunk_id)
        lance_rows.append(
            {
                "chunk_id": chunk_id,
                "book_name": context.book_name,
                "page_no": context.page_no,
                "text": text,
                "char_count": context.char_count,
                "page_count": context.page_count,
                "embedding": embedding,
            }
        )
    return chunk_ids, lance_rows


def _restore_lance_rows(
    table: Table,
    *,
    old_chunk_ids: list[int],
    new_chunk_ids: list[int],
    old_rows: list[dict[str, object]],
) -> None:
    affected_ids = old_chunk_ids + new_chunk_ids
    if affected_ids:
        table.delete(_chunk_id_filter(affected_ids))
    if old_rows:
        table.add(old_rows)


def _compensate_failed_update(
    conn: sqlite3.Connection,
    table: Table,
    context: _PageContext,
    *,
    old_chunk_ids: list[int],
    new_chunk_ids: list[int],
    old_rows: list[dict[str, object]],
) -> Exception | None:
    conn.rollback()
    compensation_error: Exception | None = None
    try:
        _restore_lance_rows(
            table,
            old_chunk_ids=old_chunk_ids,
            new_chunk_ids=new_chunk_ids,
            old_rows=old_rows,
        )
    except Exception as restore_exc:
        compensation_error = restore_exc
        logger.exception(
            "LanceDB compensation failed: %s p%d",
            context.book_name,
            context.page_no,
        )
    conn.execute(
        "UPDATE books SET indexed_at = NULL WHERE id = ?",
        (context.book_id,),
    )
    conn.commit()
    return compensation_error


def rebuild_page_from_pages(
    conn: sqlite3.Connection,
    book_name: str,
    page_no: int,
) -> None:
    """補正済み1ページのSQLite chunks・LanceDB・FTSを再同期する。

    ``pages`` 自体は変更しない。LanceDB更新に失敗した場合は旧行を補償復元し、
    ``books.indexed_at`` をNULLのままにして書籍単位rebuildが必要な状態を示す。
    """
    context = _load_page_context(conn, book_name, page_no)
    # 補正本文に対する後続処理が失敗しても、旧page ICU索引を検索へ返さない。
    mark_page_fts_stale(conn)
    conn.commit()

    chunk_texts, embeddings = _prepare_chunks(context)
    old_chunk_ids = [
        int(row[0])
        for row in conn.execute(
            "SELECT id FROM chunks WHERE page_id = ? ORDER BY id",
            (context.page_id,),
        ).fetchall()
    ]
    lance_table = get_chunks_table()
    old_lance_rows = _snapshot_lance_rows(lance_table, old_chunk_ids)
    if len(old_lance_rows) != len(old_chunk_ids):
        raise RuntimeError(f"page index is already inconsistent; run full rebuild: {book_name} p{page_no}")

    logger.info(
        "rebuild_page_from_pages start: %s p%d (old=%d, new=%d)",
        book_name,
        page_no,
        len(old_chunk_ids),
        len(chunk_texts),
    )

    # プロセス停止時にも不完全状態を検知できるよう、クロスストア更新前に確定する。
    conn.execute(
        "UPDATE books SET indexed_at = NULL WHERE id = ?",
        (context.book_id,),
    )
    conn.commit()

    new_chunk_ids: list[int] = []
    try:
        conn.execute("DELETE FROM chunks WHERE page_id = ?", (context.page_id,))
        new_chunk_ids, new_lance_rows = _insert_new_chunks(
            conn,
            context,
            chunk_texts,
            embeddings,
        )
        if old_chunk_ids:
            lance_table.delete(_chunk_id_filter(old_chunk_ids))
        if new_lance_rows:
            lance_table.add(new_lance_rows)

        # external-content FTS5から旧語を確実に除くため、FTSだけは全行を同期する。
        conn.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild')")
        conn.execute(
            "UPDATE books SET indexed_at = datetime('now', '+9 hours') WHERE id = ?",
            (context.book_id,),
        )
        conn.commit()
    except Exception as exc:
        compensation_error = _compensate_failed_update(
            conn,
            lance_table,
            context,
            old_chunk_ids=old_chunk_ids,
            new_chunk_ids=new_chunk_ids,
            old_rows=old_lance_rows,
        )
        if compensation_error is not None:
            raise RuntimeError(f"page rebuild and LanceDB compensation failed: {book_name} p{page_no}") from exc
        raise

    logger.info(
        "rebuild_page_from_pages finished: %s p%d (chunks=%d)",
        book_name,
        page_no,
        len(chunk_texts),
    )
