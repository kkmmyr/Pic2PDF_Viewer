"""チャンク文脈生成とベクトル再構築を調停するapplication service。"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from utils.logger import get_logger

from .builder import EMBED_BATCH_SIZE
from .connection import with_db
from .contextualizer import generate_chunk_context, make_embedding_input
from .embedder import embed_batch
from .lance_store import get_chunks_table

logger = get_logger(__name__)

StepCallback = Callable[[str], None]
GeneratedContext = tuple[sqlite3.Row, str]


class ChunkTable(Protocol):
    def delete(self, where: str) -> object: ...

    def add(self, data: Sequence[Mapping[str, object]]) -> object: ...


def build_book_contexts(
    book_name: str,
    *,
    redo: bool = False,
    step_callback: StepCallback | None = None,
    detail_callback: StepCallback | None = None,
) -> None:
    """チャンク文脈生成と再embeddingだけを独立ジョブとして実行する。"""

    def _log(message: str) -> None:
        logger.info("[generate_contexts:%s] %s", book_name, message)
        if step_callback:
            step_callback(message)

    def _detail(message: str) -> None:
        if detail_callback:
            detail_callback(message)

    _log("step 1/1: generate_contexts")
    with with_db() as conn:
        _run_generate_contexts(conn, book_name, redo=redo, log=_log, detail=_detail)
    _log("finished")


def _run_generate_contexts(
    conn: sqlite3.Connection,
    book_name: str,
    *,
    redo: bool,
    log: StepCallback,
    detail: StepCallback | None = None,
) -> None:
    book_row = conn.execute("SELECT id, summary FROM books WHERE name = ?", (book_name,)).fetchone()
    if book_row is None:
        log("  skip: book not found in DB")
        return
    book_id, book_summary = book_row
    if not book_summary or not book_summary.strip():
        log("  skip: book summary missing (run step 2 first)")
        return

    chunks = _load_context_chunks(conn, book_id, redo=redo)
    if not chunks:
        log("  skip: no chunks to contextualize (all done)")
        return

    total_chunks = len(chunks)
    log(f"  processing {total_chunks} chunks")
    lance_table = get_chunks_table()
    done = 0
    for batch_start in range(0, total_chunks, EMBED_BATCH_SIZE):
        generated = _generate_batch(
            chunks[batch_start : batch_start + EMBED_BATCH_SIZE],
            book_name=book_name,
            book_summary=book_summary,
            batch_start=batch_start,
            total_chunks=total_chunks,
            log=log,
            detail=detail,
        )
        if not generated:
            continue
        try:
            _store_batch(conn, lance_table, generated)
            done += len(generated)
        except Exception as exc:
            first_id = generated[0][0]["chunk_id"]
            last_id = generated[-1][0]["chunk_id"]
            log(f"  batch {first_id}-{last_id} error: {exc}")
            logger.warning(
                "[generate_contexts:%s] batch %s-%s failed: %s",
                book_name,
                first_id,
                last_id,
                exc,
            )
    log(f"  done: {done}/{total_chunks} chunks")


def _load_context_chunks(
    conn: sqlite3.Connection,
    book_id: int,
    *,
    redo: bool,
) -> list[sqlite3.Row]:
    sql = """
        SELECT
            c.id AS chunk_id,
            c.text AS chunk_text,
            b.name AS book_name,
            p.page_no,
            p.char_count,
            b.page_count
        FROM chunks c
        JOIN pages p ON c.page_id = p.id
        JOIN books b ON p.book_id = b.id
        WHERE p.book_id = ?
    """
    if not redo:
        sql += " AND c.contextual_text IS NULL"
    sql += " ORDER BY c.id"
    return conn.execute(sql, (book_id,)).fetchall()


def _generate_batch(
    batch: list[sqlite3.Row],
    *,
    book_name: str,
    book_summary: str,
    batch_start: int,
    total_chunks: int,
    log: StepCallback,
    detail: StepCallback | None,
) -> list[GeneratedContext]:
    generated: list[GeneratedContext] = []
    for row in batch:
        chunk_id = row["chunk_id"]
        chunk_text = row["chunk_text"]
        if detail:
            detail(f"コンテキスト {batch_start + len(generated)}/{total_chunks} チャンク")
        try:
            context = generate_chunk_context(book_name, book_summary, chunk_text)
            if context:
                generated.append((row, context))
        except Exception as exc:
            log(f"  chunk {chunk_id} context error: {exc}")
            logger.warning(
                "[generate_contexts:%s] chunk %s failed: %s",
                book_name,
                chunk_id,
                exc,
            )
    return generated


def _store_batch(
    conn: sqlite3.Connection,
    lance_table: ChunkTable,
    generated: list[GeneratedContext],
) -> None:
    embeddings = embed_batch([make_embedding_input(context, row["chunk_text"]) for row, context in generated])
    lance_rows = [
        {
            "chunk_id": row["chunk_id"],
            "book_name": row["book_name"],
            "page_no": row["page_no"],
            "text": row["chunk_text"],
            "char_count": row["char_count"] or 0,
            "page_count": row["page_count"] or 0,
            "embedding": embedding,
        }
        for (row, _), embedding in zip(generated, embeddings, strict=True)
    ]
    chunk_ids = ", ".join(str(row["chunk_id"]) for row, _ in generated)
    lance_table.delete(f"chunk_id IN ({chunk_ids})")
    lance_table.add(lance_rows)
    with conn:
        conn.executemany(
            "UPDATE chunks SET contextual_text = ? WHERE id = ?",
            [(context, row["chunk_id"]) for row, context in generated],
        )
