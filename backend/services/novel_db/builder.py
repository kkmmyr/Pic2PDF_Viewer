"""1 冊の novel.db レコードを構築するフロー。

PDF テキスト抽出 → pages 登録 → FTS5 同期 → チャンク分割 → embedding 計算 → chunks/chunks_vec 登録。
失敗時はトランザクションごとロールバックし、書籍は「未構築」状態に戻る（[設計書 §5.5]）。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from config import KINDLE_NOVEL_IMAGES_DIR, KINDLE_NOVEL_PDF_DIR
from utils.logger import get_logger

from .chunker import chunk_page
from .embedder import embed_batch, serialize_f32
from .extractor import extract_pages

logger = get_logger(__name__)

# 短すぎるページ（章扉・人物紹介の小さな bbox 集まり）はチャンク化しない
MIN_CHARS_FOR_CHUNK = 30

# embedding API 呼び出しのバッチサイズ
EMBED_BATCH_SIZE = 16


def _resolve_paths(book_name: str) -> tuple[Path, Path]:
    """書籍名から PDF と画像ディレクトリの絶対パスを返す。

    book_name は PDF stem = 画像サブディレクトリ名と仮定（既存運用に従う）。
    """
    pdf_path = Path(KINDLE_NOVEL_PDF_DIR) / f"{book_name}.pdf"
    images_dir = Path(KINDLE_NOVEL_IMAGES_DIR) / book_name
    return pdf_path, images_dir


def rebuild_book(
    conn: sqlite3.Connection,
    book_name: str,
    *,
    progress_callback=None,
) -> None:
    """1 冊を再構築する（既存レコードは削除して上書き）。

    Args:
        conn: novel.db への sqlite3 接続（sqlite_vec ロード済み）
        book_name: PDF stem = 画像サブディレクトリ名
        progress_callback: 進捗通知用の関数 (done: int, total: int) -> None。任意

    Raises:
        FileNotFoundError: PDF が存在しないとき
        EmbeddingError: Ollama 接続失敗 / 次元不一致など
    """
    pdf_path, images_dir = _resolve_paths(book_name)
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    logger.info("rebuild_book start: %s", book_name)

    # 既存レコードは削除（CASCADE で pages / chunks / chunks_vec も連動）
    # トランザクション開始前に削除すると、構築失敗時に元の状態へ戻れないので、
    # with conn: の中で DELETE → INSERT を一括実行する。
    with conn:
        # 先に同名書籍の既存 chunks_vec を消す（外部仮想テーブルなので CASCADE 不可）
        old_chunk_ids = [
            row[0]
            for row in conn.execute(
                "SELECT c.id FROM chunks c "
                "JOIN pages p ON c.page_id = p.id "
                "JOIN books b ON p.book_id = b.id "
                "WHERE b.name = ?",
                (book_name,),
            )
        ]
        if old_chunk_ids:
            conn.executemany(
                "DELETE FROM chunks_vec WHERE rowid = ?",
                [(cid,) for cid in old_chunk_ids],
            )

        conn.execute("DELETE FROM books WHERE name = ?", (book_name,))

        # PDF からページ抽出
        pages = extract_pages(pdf_path)

        # books に INSERT
        cur = conn.execute(
            "INSERT INTO books (name, pdf_path, images_dir, page_count, indexed_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (book_name, str(pdf_path), str(images_dir), len(pages)),
        )
        book_id = cur.lastrowid

        # pages に INSERT、id を保持
        page_ids: list[int] = []
        for p in pages:
            img = images_dir / f"{p['page_no']:03d}.png"
            cur = conn.execute(
                "INSERT INTO pages (book_id, page_no, image_path, full_text, char_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    book_id,
                    p["page_no"],
                    str(img) if img.exists() else None,
                    p["full_text"],
                    p["char_count"],
                ),
            )
            page_ids.append(cur.lastrowid)

        # FTS5 同期
        conn.execute(
            "INSERT INTO pages_fts (rowid, full_text) "
            "SELECT id, full_text FROM pages WHERE book_id = ?",
            (book_id,),
        )

        # チャンク分割
        all_chunks: list[dict] = []
        for p, page_id in zip(pages, page_ids, strict=True):
            if p["char_count"] < MIN_CHARS_FOR_CHUNK:
                continue
            for idx, c in enumerate(chunk_page(p["full_text"])):
                all_chunks.append({"page_id": page_id, "chunk_idx": idx, "text": c})

        total_chunks = len(all_chunks)
        if progress_callback:
            progress_callback(0, total_chunks)

        # embedding 計算 + 保存
        for batch_start in range(0, total_chunks, EMBED_BATCH_SIZE):
            batch = all_chunks[batch_start:batch_start + EMBED_BATCH_SIZE]
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

    logger.info(
        "rebuild_book finished: %s (pages=%d, chunks=%d)",
        book_name, len(pages), total_chunks,
    )
