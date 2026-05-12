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

from config import KINDLE_NOVEL_IMAGES_DIR
from utils.logger import get_logger

from .chunker import chunk_book
from .connection import with_db
from .embedder import embed_batch, serialize_f32
from .extractor import extract_pages_from_images, load_ocr_engine
from .schema import init_schema

logger = get_logger(__name__)

# 短すぎるページ（章扉・人物紹介の小さな bbox 集まり）はチャンク化しない
MIN_CHARS_FOR_CHUNK = 30

# embedding API 呼び出しのバッチサイズ
EMBED_BATCH_SIZE = 16

ProgressCallback = Callable[[int, int], None]


def _resolve_images_dir(book_name: str) -> Path:
    return Path(KINDLE_NOVEL_IMAGES_DIR) / book_name


# ---------------------------------------------------------------------------
# ステップ 1: OCR
# ---------------------------------------------------------------------------

def ocr_book(book_name: str, *, engine: object | None = None) -> None:
    """OCR ステップ: images/*.png を OCR して pages.full_text を更新する。

    - books レコードが存在しなければ INSERT、存在すれば page_count / ocr_done_at を更新。
    - pages は (book_id, page_no) をキーに UPSERT（full_text / char_count / image_path を更新）。
    - FTS5 を再同期する。
    - chunks/chunks_vec は触らない（rebuild_from_pages が担当）。

    Args:
        book_name: 書籍 stem（= images サブディレクトリ名）
        engine: 初期化済みの OCR エンジン。None のとき内部で yomitoku を初期化する。
                複数書籍を連続処理する場合は呼び出し側で 1 度初期化して渡すこと。
    """
    images_dir = _resolve_images_dir(book_name)
    if not images_dir.exists():
        raise FileNotFoundError(f"images dir not found: {images_dir}")

    if engine is None:
        engine = load_ocr_engine()

    logger.info("ocr_book start: %s", book_name)
    pages = extract_pages_from_images(images_dir, engine)
    if not pages:
        raise ValueError(f"no PNG images found in: {images_dir}")

    with with_db() as conn:
        init_schema(conn)
        with conn:
            existing = conn.execute(
                "SELECT id FROM books WHERE name = ?", (book_name,)
            ).fetchone()

            if existing is None:
                cur = conn.execute(
                    "INSERT INTO books "
                    "(name, pdf_path, images_dir, page_count, indexed_at, ocr_done_at) "
                    "VALUES (?, ?, ?, ?, NULL, datetime('now'))",
                    (book_name, "", str(images_dir), len(pages)),
                )
                book_id = cur.lastrowid
            else:
                book_id = existing[0]
                conn.execute(
                    "UPDATE books SET page_count = ?, ocr_done_at = datetime('now') "
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

            # FTS5 再同期
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

    logger.info("ocr_book finished: %s (pages=%d)", book_name, len(pages))


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
        "SELECT id, page_no, full_text, char_count FROM pages WHERE book_id = ? ORDER BY page_no",
        (book_id,),
    ).fetchall()
    if not pages_rows:
        raise ValueError(f"no pages found (run OCR first): {book_name}")

    logger.info("rebuild_from_pages start: %s (pages=%d)", book_name, len(pages_rows))

    with conn:
        # 既存 chunks_vec を削除（外部仮想テーブルは CASCADE 不可）
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
            conn.executemany(
                "DELETE FROM chunks_vec WHERE rowid = ?",
                [(cid,) for cid in old_chunk_ids],
            )
        conn.execute(
            "DELETE FROM chunks WHERE page_id IN "
            "(SELECT id FROM pages WHERE book_id = ?)",
            (book_id,),
        )

        # §4.4: クロスページチャンク化（全ページ連結 → chunk_book）
        page_dicts = [
            {"page_id": pid, "page_no": pno, "full_text": text or ""}
            for pid, pno, text, char_count in pages_rows
            if (char_count or 0) >= MIN_CHARS_FOR_CHUNK
        ]
        all_chunks = chunk_book(page_dicts)

        total_chunks = len(all_chunks)
        if progress_callback:
            progress_callback(0, total_chunks)

        # embedding 計算 + 保存
        for batch_start in range(0, total_chunks, EMBED_BATCH_SIZE):
            batch = all_chunks[batch_start : batch_start + EMBED_BATCH_SIZE]
            embeddings = embed_batch([c["text"] for c in batch])
            for c, emb in zip(batch, embeddings, strict=True):
                cur = conn.execute(
                    "INSERT INTO chunks (page_id, chunk_idx, text, char_count) "
                    "VALUES (?, ?, ?, ?)",
                    (c["page_id"], c["chunk_idx"], c["text"], len(c["text"])),
                )
                chunk_id = cur.lastrowid
                conn.execute(
                    "INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)",
                    (chunk_id, serialize_f32(emb)),
                )
            done = min(batch_start + EMBED_BATCH_SIZE, total_chunks)
            if progress_callback:
                progress_callback(done, total_chunks)

        conn.execute(
            "UPDATE books SET indexed_at = datetime('now') WHERE id = ?",
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
