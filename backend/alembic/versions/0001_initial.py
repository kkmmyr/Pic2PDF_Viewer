"""initial schema migrations

既存の schema.py._migrate() を Alembic 管理に移行した最初の revision。
新規 DB（テーブルなし）は no-op — 0003 revision で完全なスキーマが生成される。
既存 DB はカラム有無を確認してから ALTER TABLE を実行する（冪等）。

Revision ID: 0001
Revises:
Create Date: 2026-05-15
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _cols(conn: sa.engine.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()}


def upgrade() -> None:
    conn = op.get_bind()

    # テーブルが存在しない場合は新規 DB — 0003 revision で最新スキーマが生成されるため何もしない
    tables = {
        row[0]
        for row in conn.execute(
            sa.text("SELECT name FROM sqlite_master WHERE type='table'")
        ).fetchall()
    }
    if "books" not in tables:
        return

    # books.indexed_at の NOT NULL 制約撤去（最古の既存 DB のみ該当）
    books_info = {
        row[1]: row
        for row in conn.execute(sa.text("PRAGMA table_info(books)")).fetchall()
    }
    if books_info.get("indexed_at") and books_info["indexed_at"][3] == 1:
        conn.execute(sa.text("PRAGMA foreign_keys = OFF"))
        conn.execute(sa.text(
            "CREATE TABLE books_new ("
            "    id          INTEGER PRIMARY KEY,"
            "    name        TEXT NOT NULL UNIQUE,"
            "    pdf_path    TEXT NOT NULL,"
            "    images_dir  TEXT NOT NULL,"
            "    page_count  INTEGER NOT NULL,"
            "    indexed_at  TIMESTAMP,"
            "    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")"
        ))
        conn.execute(sa.text(
            "INSERT INTO books_new (id, name, pdf_path, images_dir, page_count, indexed_at, created_at)"
            " SELECT id, name, pdf_path, images_dir, page_count, indexed_at, created_at FROM books"
        ))
        conn.execute(sa.text("DROP TABLE books"))
        conn.execute(sa.text("ALTER TABLE books_new RENAME TO books"))
        conn.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_books_name ON books(name)"))
        conn.execute(sa.text("PRAGMA foreign_keys = ON"))

    pages_cols = _cols(conn, "pages")
    if "main_characters" not in pages_cols:
        conn.execute(sa.text("ALTER TABLE pages ADD COLUMN main_characters TEXT"))

    books_cols = _cols(conn, "books")
    if "summary" not in books_cols:
        conn.execute(sa.text("ALTER TABLE books ADD COLUMN summary TEXT"))
    if "summary_generated_at" not in books_cols:
        conn.execute(sa.text("ALTER TABLE books ADD COLUMN summary_generated_at TIMESTAMP"))
    if "ocr_done_at" not in books_cols:
        conn.execute(sa.text("ALTER TABLE books ADD COLUMN ocr_done_at TIMESTAMP"))

    chunks_cols = _cols(conn, "chunks")
    if "contextual_text" not in chunks_cols:
        conn.execute(sa.text("ALTER TABLE chunks ADD COLUMN contextual_text TEXT"))
    if "contextual_generated_at" not in chunks_cols:
        conn.execute(sa.text("ALTER TABLE chunks ADD COLUMN contextual_generated_at TIMESTAMP"))

    if "rebuild_jobs" in tables:
        rj_cols = _cols(conn, "rebuild_jobs")
        if "current_step" not in rj_cols:
            conn.execute(sa.text("ALTER TABLE rebuild_jobs ADD COLUMN current_step TEXT"))
        if "current_detail" not in rj_cols:
            conn.execute(sa.text("ALTER TABLE rebuild_jobs ADD COLUMN current_detail TEXT"))


def downgrade() -> None:
    pass  # intentionally no-op
