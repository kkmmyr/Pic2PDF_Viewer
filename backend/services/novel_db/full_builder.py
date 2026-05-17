"""§4.5 本構築統合: 1 冊の全構築パイプラインを 1 関数に統合する。

処理ステップ:
  1. rebuild_from_pages  — チャンク分割 + embedding 再構築（常実行）
  2. summarize_and_characters — 書籍サマリ + キャラクター辞典を Qwen 1 回で一括生成
                                （redo=False かつ summary・book_characters 両方存在でスキップ）
  3. generate_contexts   — チャンク位置説明生成 + 再 embedding（redo=False かつ contextual_text 存在でスキップ）

詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §5.14。
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable

from utils.logger import get_logger

from .builder import rebuild_from_pages
from .connection import with_db
from .contextualizer import generate_chunk_context, make_embedding_input
from .embedder import embed_batch
from .lance_store import get_chunks_table, get_summaries_table
from .schema import init_schema
from .summarizer import summarize_book_with_characters, update_book_summary

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
        init_schema(conn)
        rebuild_from_pages(conn, book_name, progress_callback=_rebuild_progress)

    # ステップ 2: 書籍サマリ + キャラクター辞典を Qwen 1 回で一括生成
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
    """書籍サマリ + キャラクター辞典を Qwen 1 回で一括生成して DB に保存する。"""
    row = conn.execute(
        "SELECT id, summary FROM books WHERE name = ?", (book_name,)
    ).fetchone()
    if row is None:
        log("  skip: book not found in DB")
        return
    book_id, existing_summary = row

    has_chars = conn.execute(
        "SELECT COUNT(*) FROM book_characters WHERE book_id = ? AND summary IS NOT NULL",
        (book_id,),
    ).fetchone()[0] > 0

    if existing_summary and has_chars and not redo:
        log("  skip: summary and characters already exist")
        return

    if detail:
        detail("サマリ生成中")
    try:
        summary, char_summaries = summarize_book_with_characters(conn, book_name, progress=log)
    except Exception as exc:
        log(f"  error: {exc}")
        logger.exception("[full_build:%s] combined_step failed", book_name)
        raise

    update_book_summary(conn, book_name, summary)

    if char_summaries:
        if detail:
            detail("キャラクタ抽出中")
        conn.execute("DELETE FROM book_characters WHERE book_id = ?", (book_id,))
        for name, char_summary in char_summaries.items():
            # first_page / page_count をテキスト検索で近似
            result = conn.execute(
                "SELECT MIN(page_no), COUNT(*) FROM pages "
                "WHERE book_id = ? AND full_text LIKE ?",
                (book_id, f"%{name}%"),
            ).fetchone()
            first_page = result[0] or 1
            page_count = result[1] or 1
            conn.execute(
                """INSERT INTO book_characters
                       (book_id, name, summary, first_page, page_count, generated_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now', '+9 hours'))""",
                (book_id, name, char_summary, first_page, page_count),
            )
        conn.commit()

    log(f"  done: summary={len(summary)} chars, {len(char_summaries)} characters")


def _run_generate_contexts(
    conn: sqlite3.Connection,
    book_name: str,
    *,
    redo: bool,
    log: StepCallback,
    detail: StepCallback | None = None,
) -> None:
    book_row = conn.execute(
        "SELECT id, summary FROM books WHERE name = ?", (book_name,)
    ).fetchone()
    if book_row is None:
        log("  skip: book not found in DB")
        return
    book_id, book_summary = book_row

    if not book_summary or not book_summary.strip():
        log("  skip: book summary missing (run step 2 first)")
        return

    sql = (
        "SELECT c.id, c.text FROM chunks c "
        "JOIN pages p ON c.page_id = p.id "
        "WHERE p.book_id = ?"
    )
    if not redo:
        sql += " AND c.contextual_text IS NULL"
    chunks = conn.execute(sql, (book_id,)).fetchall()

    if not chunks:
        log("  skip: no chunks to contextualize (all done)")
        return

    total_chunks = len(chunks)
    log(f"  processing {total_chunks} chunks")
    lance_table = get_chunks_table()
    done = 0
    for chunk_id, chunk_text in chunks:
        if detail:
            detail(f"コンテキスト {done}/{total_chunks} チャンク")
        try:
            ctx = generate_chunk_context(book_name, book_summary, chunk_text)
            if not ctx:
                continue
            conn.execute(
                "UPDATE chunks SET contextual_text = ? WHERE id = ?",
                (ctx, chunk_id),
            )
            emb_input = make_embedding_input(ctx, chunk_text)
            emb = embed_batch([emb_input])[0]
            # LanceDB の embedding を更新（削除して再挿入）
            lance_table.delete(f"chunk_id = {chunk_id}")
            # book_name / page_no / char_count / page_count を SQLite から取得
            meta = conn.execute(
                """
                SELECT b.name, p.page_no, p.char_count, b.page_count
                FROM chunks c
                JOIN pages p ON c.page_id = p.id
                JOIN books b ON p.book_id = b.id
                WHERE c.id = ?
                """,
                (chunk_id,),
            ).fetchone()
            if meta:
                lance_table.add([{
                    "chunk_id": chunk_id,
                    "book_name": meta[0],
                    "page_no": meta[1],
                    "text": chunk_text,
                    "char_count": meta[2] or 0,
                    "page_count": meta[3] or 0,
                    "embedding": emb,
                }])
            conn.commit()
            done += 1
        except Exception as exc:
            log(f"  chunk {chunk_id} error: {exc}")
            logger.warning(
                "[full_build:%s] generate_context chunk %s failed: %s",
                book_name, chunk_id, exc,
            )
    log(f"  done: {done}/{total_chunks} chunks")
