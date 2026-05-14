"""LanceDB 接続とテーブル管理。

sqlite-vec (chunks_vec / book_summaries_vec) の置き換えとして、
LanceDB にベクトルを格納する。ANN インデックス（IVF_PQ）を
チャンク数 > 50,000 で自動構築する。

テーブルスキーマ:
  chunks:    (chunk_id: int, book_name: str, page_no: int, text: str,
              char_count: int, page_count: int, embedding: vector[1024])
  summaries: (book_id: int, book_name: str, embedding: vector[1024])
"""
from __future__ import annotations

import threading

import lancedb
import pyarrow as pa

from config import NOVEL_DB_EMBED_DIM, NOVEL_DB_LANCE_PATH

_lock = threading.Lock()
_db: lancedb.DBConnection | None = None

# IVF_PQ インデックスを自動構築するチャンク数閾値
ANN_INDEX_THRESHOLD = 50_000


def get_db() -> lancedb.DBConnection:
    global _db
    if _db is None:
        with _lock:
            if _db is None:
                _db = lancedb.connect(NOVEL_DB_LANCE_PATH)
    return _db


def reset_db() -> None:
    """グローバル DB 接続をリセットする（テスト用）。次回 get_db() 時に再接続する。"""
    global _db
    with _lock:
        _db = None


# ---------------------------------------------------------------------------
# chunks テーブル
# ---------------------------------------------------------------------------

_CHUNKS_SCHEMA = pa.schema([
    pa.field("chunk_id", pa.int64()),
    pa.field("book_name", pa.utf8()),
    pa.field("page_no", pa.int32()),
    pa.field("text", pa.utf8()),
    pa.field("char_count", pa.int32()),
    pa.field("page_count", pa.int32()),
    pa.field("embedding", pa.list_(pa.float32(), NOVEL_DB_EMBED_DIM)),
])


def get_chunks_table() -> lancedb.table.Table:
    db = get_db()
    try:
        return db.open_table("chunks")
    except Exception:
        return db.create_table("chunks", schema=_CHUNKS_SCHEMA)


# ---------------------------------------------------------------------------
# summaries テーブル
# ---------------------------------------------------------------------------

_SUMMARIES_SCHEMA = pa.schema([
    pa.field("book_id", pa.int64()),
    pa.field("book_name", pa.utf8()),
    pa.field("embedding", pa.list_(pa.float32(), NOVEL_DB_EMBED_DIM)),
])


def get_summaries_table() -> lancedb.table.Table:
    db = get_db()
    try:
        return db.open_table("summaries")
    except Exception:
        return db.create_table("summaries", schema=_SUMMARIES_SCHEMA)


# ---------------------------------------------------------------------------
# ANN インデックス管理
# ---------------------------------------------------------------------------

def maybe_create_index(table: lancedb.table.Table) -> None:
    """チャンク数が閾値を超えたとき IVF_PQ インデックスを作成する。

    既存インデックスがある場合は何もしない。
    """
    count = table.count_rows()
    if count < ANN_INDEX_THRESHOLD:
        return
    existing = table.list_indices()
    if any(idx.get("name") == "embedding_idx" for idx in existing):
        return
    table.create_index(
        "embedding",
        config=lancedb.index.IvfPq(num_partitions=256, num_sub_vectors=64),
        index_name="embedding_idx",
        replace=False,
    )
