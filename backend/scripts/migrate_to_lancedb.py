"""sqlite-vec → LanceDB マイグレーションスクリプト。

実行:
    cd backend
    uv run python scripts/migrate_to_lancedb.py

処理:
  1. novel.db の chunks テーブルから chunk_id / book_name / page_no / text /
     char_count を取得し、chunks_vec から embedding を取得して LanceDB に登録
  2. books / book_summaries_vec から book_id / book_name / embedding を取得して
     LanceDB に登録

既存の LanceDB テーブルに既にデータがある場合は差分を確認して追記する。
ロールバック: `data/novel.lancedb/` ディレクトリを削除して再実行。
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

# backend/ をパスに追加（スクリプト直接実行対応）
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.novel_db.connection import with_db
from services.novel_db.lance_store import get_chunks_table, get_summaries_table, maybe_create_index


def _unpack_f32(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def migrate_chunks() -> int:
    """chunks_vec → LanceDB chunks テーブルへ移行する。既存 chunk_id はスキップ。"""
    table = get_chunks_table()
    existing_ids: set[int] = set()
    count = table.count_rows()
    if count > 0:
        existing_ids = {row["chunk_id"] for row in table.search().select(["chunk_id"]).limit(count).to_list()}

    rows: list[dict] = []
    with with_db() as conn:
        sql = """
            SELECT c.id, b.name, p.page_no, c.text, c.char_count, b.page_count,
                   cv.embedding
            FROM chunks c
            JOIN chunks_vec cv ON cv.rowid = c.id
            JOIN pages p ON c.page_id = p.id
            JOIN books b ON p.book_id = b.id
        """
        for chunk_id, book_name, page_no, text, char_count, page_count, emb_blob in conn.execute(sql):
            if chunk_id in existing_ids:
                continue
            rows.append({
                "chunk_id": chunk_id,
                "book_name": book_name,
                "page_no": page_no,
                "text": text or "",
                "char_count": char_count or 0,
                "page_count": page_count or 0,
                "embedding": _unpack_f32(emb_blob),
            })

    if rows:
        table.add(rows)
        print(f"chunks: {len(rows)} 件を移行しました")
        maybe_create_index(table)
    else:
        print("chunks: 新規データなし（スキップ）")
    return len(rows)


def migrate_summaries() -> int:
    """book_summaries_vec → LanceDB summaries テーブルへ移行する。既存 book_id はスキップ。"""
    table = get_summaries_table()
    existing_ids: set[int] = set()
    count = table.count_rows()
    if count > 0:
        existing_ids = {row["book_id"] for row in table.search().select(["book_id"]).limit(count).to_list()}

    rows: list[dict] = []
    with with_db() as conn:
        # book_summaries_vec テーブルが存在するか確認
        has_vec = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='book_summaries_vec'"
        ).fetchone()
        if has_vec is None:
            print("summaries: book_summaries_vec テーブルが存在しません（スキップ）")
            return 0

        sql = """
            SELECT b.id, b.name, bsv.embedding
            FROM book_summaries_vec bsv
            JOIN books b ON b.id = bsv.rowid
        """
        for book_id, book_name, emb_blob in conn.execute(sql):
            if book_id in existing_ids:
                continue
            rows.append({
                "book_id": book_id,
                "book_name": book_name,
                "embedding": _unpack_f32(emb_blob),
            })

    if rows:
        table.add(rows)
        print(f"summaries: {len(rows)} 件を移行しました")
    else:
        print("summaries: 新規データなし（スキップ）")
    return len(rows)


if __name__ == "__main__":
    print("=== LanceDB マイグレーション開始 ===")
    chunk_count = migrate_chunks()
    summary_count = migrate_summaries()
    print(f"=== 完了: chunks={chunk_count}, summaries={summary_count} ===")
