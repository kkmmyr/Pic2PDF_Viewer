"""§4.5 本構築統合: 1 冊の全構築パイプラインを 1 関数に統合する。

処理ステップ:
  1. rebuild_from_pages  — チャンク分割 + embedding 再構築（常実行）
  2. summarize_and_characters — 事実抽出後に書籍サマリと人物辞典を個別生成・校正し、
                                全件合格後に一括確定
  3. generate_contexts   — チャンク位置説明生成 + 再 embedding（redo=False かつ contextual_text 存在でスキップ）

詳細は docs/design/詳細設計/機能別/小説RAG_パイプライン設計.md §4・§7。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from utils.logger import get_logger

from .builder import EMBED_BATCH_SIZE, rebuild_from_pages
from .character_names import derive_character_evidence_aliases, normalize_character_entries
from .connection import with_db
from .contextualizer import generate_chunk_context, make_embedding_input
from .embedder import embed_batch
from .lance_store import get_chunks_table
from .summarizer import index_book_summary, summarize_book_with_characters

logger = get_logger(__name__)

StepCallback = Callable[[str], None]


def build_book_full(
    book_name: str,
    *,
    redo: bool = False,
    step_callback: StepCallback | None = None,
    detail_callback: StepCallback | None = None,
) -> None:
    """1 冊の全構築パイプラインを実行する。

    Args:
        book_name: 書籍 stem（= images サブディレクトリ名）
        redo: True のとき既存の summary / book_characters / contextual_text を上書きする
        step_callback: ステップ名更新用コールバック（current_step に書き込む）
        detail_callback: 細粒度進捗更新用コールバック（current_detail に書き込む）
    """

    def _log(msg: str) -> None:
        logger.info("[full_build:%s] %s", book_name, msg)
        if step_callback:
            step_callback(msg)

    def _detail(msg: str) -> None:
        if detail_callback:
            detail_callback(msg)

    _log("start")

    # ステップ 1: チャンク分割 + embedding 再構築（常実行）
    _log("step 1/2: rebuild_from_pages")

    def _rebuild_progress(done: int, total: int) -> None:
        _detail(f"embedding {done}/{total} チャンク")

    with with_db() as conn:
        rebuild_from_pages(conn, book_name, progress_callback=_rebuild_progress)

    # ステップ 2: 事実抽出 → 要約/人物個別生成 → 校正 → 一括確定
    _log("step 2/2: summarize_book + characters")
    with with_db() as conn:
        _run_combined_step(conn, book_name, redo=redo, log=_log, detail=_detail)

    _log("finished")


def build_book_contexts(
    book_name: str,
    *,
    redo: bool = False,
    step_callback: StepCallback | None = None,
    detail_callback: StepCallback | None = None,
) -> None:
    """Step 3（コンテキスト生成 + 再 embedding）のみを実行する（B-23 分離ジョブ）。

    build_book_full() で Step 1+2 完了後に手動投入する想定。
    `contextual_text IS NULL` のチャンクのみ対象（途中失敗からのリカバリ対応）。
    """

    def _log(msg: str) -> None:
        logger.info("[generate_contexts:%s] %s", book_name, msg)
        if step_callback:
            step_callback(msg)

    def _detail(msg: str) -> None:
        if detail_callback:
            detail_callback(msg)

    _log("step 1/1: generate_contexts")
    with with_db() as conn:
        _run_generate_contexts(conn, book_name, redo=redo, log=_log, detail=_detail)
    _log("finished")


# ---------------------------------------------------------------------------
# ステップ実装
# ---------------------------------------------------------------------------


def _run_combined_step(
    conn: sqlite3.Connection,
    book_name: str,
    *,
    redo: bool,
    log: StepCallback,
    detail: StepCallback | None = None,
) -> None:
    """Generate all prose first, then atomically replace published SQLite rows."""
    row = conn.execute(
        "SELECT id, summary, catalog_summary FROM books WHERE name = ?",
        (book_name,),
    ).fetchone()
    if row is None:
        log("  skip: book not found in DB")
        return
    book_id, existing_summary, existing_catalog_summary = row
    existing_character_names = [
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

    if existing_summary and existing_catalog_summary and has_chars and not redo:
        log("  skip: detailed summary, catalog summary, and characters already exist")
        return

    if detail:
        detail("サマリ生成中")
    try:
        summary, catalog_summary, char_summaries = summarize_book_with_characters(
            conn,
            book_name,
            progress=log,
        )
    except Exception as exc:
        log(f"  error: {exc}")
        logger.exception("[full_build:%s] combined_step failed", book_name)
        raise

    if detail:
        detail("生成結果を検査中")
    prepared_characters = _prepare_character_rows(
        conn,
        book_id,
        char_summaries,
        log=log,
        canonical_names=existing_character_names,
    )
    if not prepared_characters:
        raise ValueError("no publishable characters; existing generated content was preserved")
    _guard_character_deletion_regression(
        conn,
        book_id,
        existing_names=existing_character_names,
        prepared_names=[row[0] for row in prepared_characters],
        log=log,
    )

    try:
        conn.execute(
            """
            UPDATE books
            SET summary = ?,
                summary_generated_at = datetime('now', '+9 hours'),
                catalog_summary = ?,
                catalog_summary_generated_at = datetime('now', '+9 hours')
            WHERE id = ?
            """,
            (summary, catalog_summary, book_id),
        )
        conn.execute("DELETE FROM book_characters WHERE book_id = ?", (book_id,))
        conn.executemany(
            """INSERT INTO book_characters
                   (book_id, name, summary, first_page, page_count, generated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now', '+9 hours'))""",
            [
                (book_id, name, char_summary, first_page, page_count)
                for name, char_summary, first_page, page_count in prepared_characters
            ],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    index_book_summary(conn, book_id, summary)
    saved_count = len(prepared_characters)

    log(f"  done: detailed={len(summary)} chars, catalog={len(catalog_summary)} chars, {saved_count} characters")


def _prepare_character_rows(
    conn: sqlite3.Connection,
    book_id: int,
    char_summaries: dict[str, str],
    *,
    log: StepCallback,
    canonical_names: list[str] | None = None,
) -> list[tuple[str, str, int, int]]:
    """Validate page evidence and prepare rows without mutating the database."""
    entries = normalize_character_entries(
        char_summaries,
        canonical_names=canonical_names or [],
    )
    page_rows = conn.execute(
        "SELECT page_no, full_text FROM pages WHERE book_id = ? AND index_eligible = 1 ORDER BY page_no",
        (book_id,),
    ).fetchall()
    prepared: list[tuple[str, str, int, int]] = []
    for entry in entries:
        derived_aliases = derive_character_evidence_aliases(entry.name)
        derived_page_counts = {
            alias: sum(alias in str(page[1] or "") for page in page_rows) for alias in derived_aliases
        }
        evidence_aliases = (
            *entry.aliases,
            *(alias for alias, count in derived_page_counts.items() if count >= 2),
        )
        evidence_pages = [
            int(page[0]) for page in page_rows if any(alias in str(page[1] or "") for alias in evidence_aliases)
        ]
        if not evidence_pages:
            log(f"  omit character without page evidence: {entry.name}")
            continue
        prepared.append(
            (
                entry.name,
                entry.summary,
                min(evidence_pages),
                len(evidence_pages),
            )
        )
    return prepared


def _guard_character_deletion_regression(
    conn: sqlite3.Connection,
    book_id: int,
    *,
    existing_names: list[str],
    prepared_names: list[str],
    log: StepCallback,
) -> None:
    """Reject unexplained deletion of published characters with current page evidence."""
    if not existing_names:
        return

    published = normalize_character_entries(
        {name: name for name in existing_names},
        canonical_names=existing_names,
    )
    prepared = normalize_character_entries(
        {name: name for name in prepared_names},
        canonical_names=[entry.name for entry in published],
    )
    prepared_set = {entry.name for entry in prepared}
    page_texts = [
        str(row[0] or "")
        for row in conn.execute(
            "SELECT full_text FROM pages WHERE book_id = ? AND index_eligible = 1",
            (book_id,),
        ).fetchall()
    ]

    unexplained: list[str] = []
    for entry in published:
        if entry.name in prepared_set:
            continue
        exact_count = sum(entry.name in text for text in page_texts)
        derived_counts = {
            alias: sum(alias in text for text in page_texts) for alias in derive_character_evidence_aliases(entry.name)
        }
        if exact_count > 0 or any(count >= 2 for count in derived_counts.values()):
            unexplained.append(entry.name)
        else:
            log(f"  allow removal without current page evidence: {entry.name}")

    if unexplained:
        names = ", ".join(unexplained)
        raise ValueError(
            "character deletion regression failed; evidenced published characters missing: "
            f"{names}; existing generated content was preserved"
        )


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
    chunks = conn.execute(sql, (book_id,)).fetchall()

    if not chunks:
        log("  skip: no chunks to contextualize (all done)")
        return

    total_chunks = len(chunks)
    log(f"  processing {total_chunks} chunks")
    lance_table = get_chunks_table()
    done = 0
    for batch_start in range(0, total_chunks, EMBED_BATCH_SIZE):
        batch = chunks[batch_start : batch_start + EMBED_BATCH_SIZE]
        generated: list[tuple[sqlite3.Row, str]] = []

        for row in batch:
            chunk_id = row["chunk_id"]
            chunk_text = row["chunk_text"]
            if detail:
                detail(f"コンテキスト {batch_start + len(generated)}/{total_chunks} チャンク")
            try:
                ctx = generate_chunk_context(book_name, book_summary, chunk_text)
                if ctx:
                    generated.append((row, ctx))
            except Exception as exc:
                log(f"  chunk {chunk_id} context error: {exc}")
                logger.warning(
                    "[full_build:%s] generate_context chunk %s failed: %s",
                    book_name,
                    chunk_id,
                    exc,
                )

        if not generated:
            continue

        try:
            embeddings = embed_batch([make_embedding_input(ctx, row["chunk_text"]) for row, ctx in generated])
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
                    [(ctx, row["chunk_id"]) for row, ctx in generated],
                )
            done += len(generated)
        except Exception as exc:
            first_id = generated[0][0]["chunk_id"]
            last_id = generated[-1][0]["chunk_id"]
            log(f"  batch {first_id}-{last_id} error: {exc}")
            logger.warning(
                "[full_build:%s] generate_context batch %s-%s failed: %s",
                book_name,
                first_id,
                last_id,
                exc,
            )
    log(f"  done: {done}/{total_chunks} chunks")
