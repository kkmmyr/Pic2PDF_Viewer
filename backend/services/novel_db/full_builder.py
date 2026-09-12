"""§4.5 本構築統合: 1冊の再構築・要約・人物生成を1関数に統合する。

処理ステップ:
  1. rebuild_from_pages  — チャンク分割 + embedding 再構築（常実行）
  2. summarize_and_characters — 事実抽出後に書籍サマリと人物辞典を個別生成・校正し、
                                全件合格後に一括確定
詳細は docs/design/詳細設計/機能別/小説RAG_パイプライン設計.md §4・§7。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from utils.logger import get_logger

from .builder import rebuild_from_pages
from .connection import with_db
from .context_generation import build_book_contexts
from .full_build_content import GeneratedBookContent, guard_character_deletion_regression, prepare_character_rows
from .full_build_repository import (
    load_character_deletion_texts,
    load_character_evidence_pages,
    load_published_book_state,
    replace_published_content,
)
from .summarizer import index_book_summary, summarize_book_with_characters

logger = get_logger(__name__)

StepCallback = Callable[[str], None]
__all__ = ["build_book_contexts", "build_book_full"]


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
    existing = load_published_book_state(conn, book_name)
    if existing is None:
        log("  skip: book not found in DB")
        return
    book_id = existing.book_id
    if existing.summary and existing.catalog_summary and existing.has_character_summary and not redo:
        log("  skip: detailed summary, catalog summary, and characters already exist")
        return

    if detail:
        detail("サマリ生成中")
    try:
        content = GeneratedBookContent(
            *summarize_book_with_characters(conn, book_name, progress=log),
        )
    except Exception as exc:
        log(f"  error: {exc}")
        logger.exception("[full_build:%s] combined_step failed", book_name)
        raise

    if detail:
        detail("生成結果を検査中")
    prepared_characters = prepare_character_rows(
        content.characters,
        load_character_evidence_pages(conn, book_id),
        log=log,
        canonical_names=existing.character_names,
    )
    if not prepared_characters:
        raise ValueError("no publishable characters; existing generated content was preserved")
    if existing.character_names:
        guard_character_deletion_regression(
            load_character_deletion_texts(conn, book_id),
            existing_names=existing.character_names,
            prepared_names=[row.name for row in prepared_characters],
            log=log,
        )

    try:
        replace_published_content(conn, book_id, content, prepared_characters)
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    index_book_summary(conn, book_id, content.summary)
    saved_count = len(prepared_characters)

    log(
        f"  done: detailed={len(content.summary)} chars, catalog={len(content.catalog_summary)} chars, "
        f"{saved_count} characters"
    )
