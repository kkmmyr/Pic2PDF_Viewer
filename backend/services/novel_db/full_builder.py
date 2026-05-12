"""§4.5 本構築統合: 1 冊の全構築パイプラインを 1 関数に統合する。

5 つの CLI バッチ（build_novel_db / extract_characters / build_novel_summaries /
build_character_summaries / build_chunk_contexts）を順番に実行する。

処理ステップ:
  1. rebuild_from_pages  — チャンク分割 + embedding 再構築（常実行）
  2. summarize_book      — 書籍俯瞰サマリ生成（redo=False かつ summary 存在でスキップ）
  3. extract_characters  — ページ主要登場人物抽出（redo=False かつ main_characters 存在でスキップ）
  4. summarize_characters — キャラクター辞典生成（redo=False かつ summary 存在でスキップ）
  5. generate_contexts   — チャンク位置説明生成 + 再 embedding（redo=False かつ contextual_text 存在でスキップ）

詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §5.14。
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable

from utils.logger import get_logger

from .builder import rebuild_from_pages
from .character_extractor import extract_main_characters
from .character_summarizer import (
    collect_character_pages,
    list_book_characters_in_db,
    summarize_character,
    upsert_character,
)
from .connection import with_db
from .contextualizer import generate_chunk_context, make_embedding_input
from .embedder import embed_batch, serialize_f32
from .schema import init_schema
from .summarizer import summarize_book, update_book_summary

logger = get_logger(__name__)

StepCallback = Callable[[str], None]


def build_book_full(
    book_name: str,
    *,
    redo: bool = False,
    step_callback: StepCallback | None = None,
) -> None:
    """1 冊の全構築パイプラインを実行する。

    Args:
        book_name: 書籍 stem（= images サブディレクトリ名）
        redo: True のとき既存の summary / main_characters / contextual_text を上書きする
        step_callback: 進捗ログ用コールバック（"step: ..." 形式のメッセージを受け取る）
    """

    def _log(msg: str) -> None:
        logger.info("[full_build:%s] %s", book_name, msg)
        if step_callback:
            step_callback(msg)

    _log("start")

    # ステップ 1: チャンク分割 + embedding 再構築（常実行）
    _log("step 1/5: rebuild_from_pages")
    with with_db() as conn:
        init_schema(conn)
        rebuild_from_pages(conn, book_name)

    # ステップ 2: 書籍俯瞰サマリ生成
    _log("step 2/5: summarize_book")
    with with_db() as conn:
        _run_summarize_book(conn, book_name, redo=redo, log=_log)

    # ステップ 3: ページ主要登場人物抽出
    _log("step 3/5: extract_characters")
    with with_db() as conn:
        _run_extract_characters(conn, book_name, redo=redo, log=_log)

    # ステップ 4: キャラクター辞典生成
    _log("step 4/5: summarize_characters")
    with with_db() as conn:
        _run_summarize_characters(conn, book_name, redo=redo, log=_log)

    # ステップ 5: チャンク位置説明生成 + 再 embedding
    _log("step 5/5: generate_contexts")
    with with_db() as conn:
        _run_generate_contexts(conn, book_name, redo=redo, log=_log)

    _log("finished")


# ---------------------------------------------------------------------------
# ステップ実装
# ---------------------------------------------------------------------------

def _run_summarize_book(
    conn: sqlite3.Connection,
    book_name: str,
    *,
    redo: bool,
    log: StepCallback,
) -> None:
    row = conn.execute(
        "SELECT id, summary FROM books WHERE name = ?", (book_name,)
    ).fetchone()
    if row is None:
        log("  skip: book not found in DB")
        return
    _, existing_summary = row

    if existing_summary and not redo:
        log("  skip: summary already exists")
        return

    try:
        summary = summarize_book(conn, book_name)
        update_book_summary(conn, book_name, summary)
        log(f"  done: {len(summary)} chars")
    except Exception as exc:
        log(f"  error: {exc}")
        logger.exception("[full_build:%s] summarize_book failed", book_name)


def _run_extract_characters(
    conn: sqlite3.Connection,
    book_name: str,
    *,
    redo: bool,
    log: StepCallback,
) -> None:
    book_row = conn.execute(
        "SELECT id FROM books WHERE name = ?", (book_name,)
    ).fetchone()
    if book_row is None:
        log("  skip: book not found in DB")
        return
    book_id = book_row[0]

    sql = (
        "SELECT id, page_no, full_text FROM pages "
        "WHERE book_id = ? AND full_text IS NOT NULL AND full_text != ''"
    )
    if not redo:
        sql += " AND main_characters IS NULL"
    sql += " ORDER BY page_no"
    pages = conn.execute(sql, (book_id,)).fetchall()

    if not pages:
        log("  skip: no pages to extract (all done)")
        return

    log(f"  processing {len(pages)} pages")
    done = 0
    for page_id, page_no, full_text in pages:
        try:
            names = extract_main_characters(full_text)
            conn.execute(
                "UPDATE pages SET main_characters = ? WHERE id = ?",
                (",".join(names), page_id),
            )
            conn.commit()
            done += 1
        except Exception as exc:
            log(f"  page {page_no} error: {exc}")
            logger.warning(
                "[full_build:%s] extract_characters page %s failed: %s",
                book_name, page_no, exc,
            )
    log(f"  done: {done}/{len(pages)} pages")


def _run_summarize_characters(
    conn: sqlite3.Connection,
    book_name: str,
    *,
    redo: bool,
    log: StepCallback,
) -> None:
    book_row = conn.execute(
        "SELECT id FROM books WHERE name = ?", (book_name,)
    ).fetchone()
    if book_row is None:
        log("  skip: book not found in DB")
        return
    book_id = book_row[0]

    stats = list_book_characters_in_db(conn, book_id)
    if not stats:
        log("  skip: no characters extracted (run step 3 first)")
        return

    existing: dict[str, bool] = {}
    for row in conn.execute(
        "SELECT name, summary FROM book_characters WHERE book_id = ?", (book_id,)
    ):
        existing[row[0]] = bool(row[1])

    targets = [
        s for s in stats
        if redo or not existing.get(s.name, False)
    ]
    if not targets:
        log("  skip: all characters already have summaries")
        return

    log(f"  processing {len(targets)} characters")
    done = 0
    for stat in targets:
        try:
            pages = collect_character_pages(conn, book_id, stat.name)
            if not pages:
                upsert_character(conn, book_id, stat, None)
                continue
            summary = summarize_character(book_name, stat.name, pages)
            upsert_character(conn, book_id, stat, summary)
            done += 1
        except Exception as exc:
            log(f"  char '{stat.name}' error: {exc}")
            logger.warning(
                "[full_build:%s] summarize_character '%s' failed: %s",
                book_name, stat.name, exc,
            )
    log(f"  done: {done}/{len(targets)} characters")


def _run_generate_contexts(
    conn: sqlite3.Connection,
    book_name: str,
    *,
    redo: bool,
    log: StepCallback,
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

    log(f"  processing {len(chunks)} chunks")
    done = 0
    for chunk_id, chunk_text in chunks:
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
            conn.execute(
                "INSERT OR REPLACE INTO chunks_vec (rowid, embedding) VALUES (?, ?)",
                (chunk_id, serialize_f32(emb)),
            )
            conn.commit()
            done += 1
        except Exception as exc:
            log(f"  chunk {chunk_id} error: {exc}")
            logger.warning(
                "[full_build:%s] generate_context chunk %s failed: %s",
                book_name, chunk_id, exc,
            )
    log(f"  done: {done}/{len(chunks)} chunks")
