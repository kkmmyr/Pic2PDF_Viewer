"""1 冊の novel.db レコードを構築するフロー。

2 ステップに分割（§4.2）:
  1. ocr_book()          : images/*.png → OCR → pages テーブルに full_text を保存
  2. rebuild_from_pages(): pages.full_text → chunk → embed → chunks/chunks_vec を再構築

各ステップは独立して実行可能。rebuild_from_pages は OCR 済みの full_text を前提とし、
pages テーブルは一切変更しない（chunks/chunks_vec のみ再構築）。

詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §5.5。
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import config
from utils.logger import get_logger

from .chunker import chunk_page
from .connection import with_db
from .embedder import embed_batch
from .extractor import PageText, run_ocr_subprocess
from .lance_store import get_chunks_table

logger = get_logger(__name__)

# 短すぎるページ（章扉・人物紹介の小さな bbox 集まり）はチャンク化しない
MIN_CHARS_FOR_CHUNK = 30

# embedding API 呼び出しのバッチサイズ
EMBED_BATCH_SIZE = 16

ProgressCallback = Callable[[int, int], None]


def _resolve_images_dir(book_name: str) -> Path:
    return Path(config.KINDLE_NOVEL_IMAGES_DIR) / book_name


# ---------------------------------------------------------------------------
# ステップ 1: OCR
# ---------------------------------------------------------------------------

def _store_ocr_pages(book_name: str, pages: list[PageText]) -> None:
    """OCR 結果を DB に保存する（books/pages テーブル更新 + FTS5 再同期）。"""
    images_dir = _resolve_images_dir(book_name)
    with with_db() as conn:
        with conn:
            existing = conn.execute(
                "SELECT id FROM books WHERE name = ?", (book_name,)
            ).fetchone()

            if existing is None:
                cur = conn.execute(
                    "INSERT INTO books "
                    "(name, pdf_path, images_dir, page_count, indexed_at, ocr_done_at) "
                    "VALUES (?, ?, ?, ?, NULL, datetime('now', '+9 hours'))",
                    (book_name, "", str(images_dir), len(pages)),
                )
                book_id = cur.lastrowid
            else:
                book_id = existing[0]
                conn.execute(
                    "UPDATE books SET page_count = ?, ocr_done_at = datetime('now', '+9 hours') "
                    "WHERE id = ?",
                    (len(pages), book_id),
                )

            for p in pages:
                img = images_dir / f"{p['page_no']:03d}.png"
                conn.execute(
                    """
                    INSERT INTO pages (book_id, page_no, image_path, full_text, char_count)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(book_id, page_no) DO UPDATE SET
                        full_text  = excluded.full_text,
                        char_count = excluded.char_count,
                        image_path = excluded.image_path
                    """,
                    (
                        book_id,
                        p["page_no"],
                        str(img) if img.exists() else None,
                        p["full_text"],
                        p["char_count"],
                    ),
                )

            conn.execute(
                "DELETE FROM pages_fts WHERE rowid IN "
                "(SELECT id FROM pages WHERE book_id = ?)",
                (book_id,),
            )
            conn.execute(
                "INSERT INTO pages_fts (rowid, full_text) "
                "SELECT id, full_text FROM pages WHERE book_id = ?",
                (book_id,),
            )

    logger.info("_store_ocr_pages finished: %s (pages=%d)", book_name, len(pages))


def ocr_book(book_name: str) -> None:
    """1 冊を OCR して DB に保存する（subprocess 経由）。複数冊連続処理は job_queue が担う。"""
    images_dir = _resolve_images_dir(book_name)
    if not images_dir.exists():
        raise FileNotFoundError(f"images dir not found: {images_dir}")

    logger.info("ocr_book start: %s", book_name)
    for _, pages in run_ocr_subprocess([images_dir]):
        if not pages:
            raise ValueError(f"no PNG images found in: {images_dir}")
        _store_ocr_pages(book_name, pages)
    logger.info("ocr_book finished: %s", book_name)


# ---------------------------------------------------------------------------
# ステップ 2: チャンク化 / embedding 再構築
# ---------------------------------------------------------------------------

def rebuild_from_pages(
    conn: sqlite3.Connection,
    book_name: str,
    *,
    progress_callback: ProgressCallback | None = None,
) -> None:
    """チャンク化・embedding ステップ: pages.full_text → chunks/chunks_vec を再構築する。

    pages テーブルは変更しない（OCR 済みの full_text を前提とする）。
    books.indexed_at を現在時刻に更新する。

    Raises:
        ValueError: books レコードが存在しない、または pages が 0 件のとき。
    """
    book_row = conn.execute(
        "SELECT id FROM books WHERE name = ?", (book_name,)
    ).fetchone()
    if book_row is None:
        raise ValueError(f"book not found (run OCR first): {book_name}")
    book_id = book_row[0]

    pages_rows = conn.execute(
        "SELECT id, full_text, char_count FROM pages WHERE book_id = ? ORDER BY page_no",
        (book_id,),
    ).fetchall()
    if not pages_rows:
        raise ValueError(f"no pages found (run OCR first): {book_name}")

    logger.info("rebuild_from_pages start: %s (pages=%d)", book_name, len(pages_rows))

    lance_table = get_chunks_table()

    with conn:
        # 既存 chunks を LanceDB から削除
        old_chunk_ids = [
            row[0]
            for row in conn.execute(
                "SELECT c.id FROM chunks c "
                "JOIN pages p ON c.page_id = p.id "
                "WHERE p.book_id = ?",
                (book_id,),
            )
        ]
        if old_chunk_ids:
            ids_str = ", ".join(str(cid) for cid in old_chunk_ids)
            lance_table.delete(f"chunk_id IN ({ids_str})")
        conn.execute(
            "DELETE FROM chunks WHERE page_id IN "
            "(SELECT id FROM pages WHERE book_id = ?)",
            (book_id,),
        )

        # チャンク分割（ページ単位）
        all_chunks: list[dict] = []
        # book_name と page_count をページIDから引くためのマップ
        book_row2 = conn.execute(
            "SELECT name, page_count FROM books WHERE id = ?", (book_id,)
        ).fetchone()
        book_name_val = book_row2[0] if book_row2 else ""
        book_page_count = book_row2[1] if book_row2 else 0

        page_meta: dict[int, tuple[int, int]] = {}  # page_id → (page_no, char_count_per_page)
        for page_id, full_text, char_count in pages_rows:
            if (char_count or 0) < MIN_CHARS_FOR_CHUNK:
                continue
            page_no_row = conn.execute(
                "SELECT page_no FROM pages WHERE id = ?", (page_id,)
            ).fetchone()
            page_no = page_no_row[0] if page_no_row else 0
            page_meta[page_id] = (page_no, char_count or 0)
            for idx, c in enumerate(chunk_page(full_text or "")):
                all_chunks.append({
                    "page_id": page_id,
                    "page_no": page_no,
                    "chunk_idx": idx,
                    "text": c,
                })

        total_chunks = len(all_chunks)
        if progress_callback:
            progress_callback(0, total_chunks)

        # embedding 計算 + 保存
        for batch_start in range(0, total_chunks, EMBED_BATCH_SIZE):
            batch = all_chunks[batch_start : batch_start + EMBED_BATCH_SIZE]
            embeddings = embed_batch([c["text"] for c in batch])
            lance_rows: list[dict] = []
            for c, emb in zip(batch, embeddings, strict=True):
                cur = conn.execute(
                    "INSERT INTO chunks (page_id, chunk_idx, text, char_count) "
                    "VALUES (?, ?, ?, ?)",
                    (c["page_id"], c["chunk_idx"], c["text"], len(c["text"])),
                )
                chunk_id = cur.lastrowid
                page_no = c["page_no"]
                page_char_count = page_meta.get(c["page_id"], (0, 0))[1]
                lance_rows.append({
                    "chunk_id": chunk_id,
                    "book_name": book_name_val,
                    "page_no": page_no,
                    "text": c["text"],
                    "char_count": page_char_count,
                    "page_count": book_page_count,
                    "embedding": emb,
                })
            if lance_rows:
                lance_table.add(lance_rows)
            done = min(batch_start + EMBED_BATCH_SIZE, total_chunks)
            if progress_callback:
                progress_callback(done, total_chunks)

        conn.execute(
            "UPDATE books SET indexed_at = datetime('now', '+9 hours') WHERE id = ?",
            (book_id,),
        )

    logger.info(
        "rebuild_from_pages finished: %s (pages=%d, chunks=%d)",
        book_name, len(pages_rows), total_chunks,
    )


# ---------------------------------------------------------------------------
# 後方互換エイリアス（既存テスト / CLI スクリプト用）
# ---------------------------------------------------------------------------

def rebuild_book(
    conn: sqlite3.Connection,
    book_name: str,
    *,
    progress_callback: ProgressCallback | None = None,
) -> None:
    """rebuild_from_pages() への後方互換エイリアス。"""
    rebuild_from_pages(conn, book_name, progress_callback=progress_callback)
