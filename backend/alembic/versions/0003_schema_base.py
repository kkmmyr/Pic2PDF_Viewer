"""0003: schema base — create all tables for new databases

既存 DB（0001/0002 適用済み）は全テーブルが存在するため no-op。
新規 DB はこのリビジョンで完全なスキーマが生成される。
これにより schema.py の起動時 DDL（init_schema）が不要になり、
Alembic がスキーマの唯一の真実の源となる。

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-11
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _tables(conn: sa.engine.Connection) -> set[str]:
    return {row[0] for row in conn.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()}


def upgrade() -> None:
    conn = op.get_bind()
    existing = _tables(conn)

    if "books" not in existing:
        conn.execute(
            sa.text("""
            CREATE TABLE books (
                id                   INTEGER PRIMARY KEY,
                name                 TEXT NOT NULL UNIQUE,
                pdf_path             TEXT NOT NULL,
                images_dir           TEXT NOT NULL,
                page_count           INTEGER NOT NULL,
                indexed_at           TIMESTAMP,
                created_at           TIMESTAMP DEFAULT (datetime('now', '+9 hours')),
                summary              TEXT,
                summary_generated_at TIMESTAMP,
                ocr_done_at          TIMESTAMP
            )
        """)
        )
        conn.execute(sa.text("CREATE INDEX idx_books_name ON books(name)"))

    if "pages" not in existing:
        conn.execute(
            sa.text("""
            CREATE TABLE pages (
                id              INTEGER PRIMARY KEY,
                book_id         INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                page_no         INTEGER NOT NULL,
                image_path      TEXT,
                full_text       TEXT,
                char_count      INTEGER NOT NULL,
                main_characters TEXT,
                UNIQUE(book_id, page_no)
            )
        """)
        )
        conn.execute(sa.text("CREATE INDEX idx_pages_book ON pages(book_id)"))

    if "pages_fts" not in existing:
        conn.execute(
            sa.text("""
            CREATE VIRTUAL TABLE pages_fts USING fts5(
                full_text,
                content='pages',
                content_rowid='id',
                tokenize='trigram'
            )
        """)
        )

    if "chunks" not in existing:
        conn.execute(
            sa.text("""
            CREATE TABLE chunks (
                id                      INTEGER PRIMARY KEY,
                page_id                 INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
                chunk_idx               INTEGER NOT NULL,
                text                    TEXT NOT NULL,
                char_count              INTEGER NOT NULL,
                contextual_text         TEXT,
                contextual_generated_at TIMESTAMP
            )
        """)
        )
        conn.execute(sa.text("CREATE INDEX idx_chunks_page ON chunks(page_id)"))

    if "qa_history" not in existing:
        conn.execute(
            sa.text("""
            CREATE TABLE qa_history (
                id            INTEGER PRIMARY KEY,
                asked_at      TIMESTAMP DEFAULT (datetime('now', '+9 hours')),
                finished_at   TIMESTAMP,
                scope_type    TEXT NOT NULL,
                scope_id      TEXT,
                question      TEXT NOT NULL,
                answer        TEXT,
                prompt        TEXT NOT NULL,
                context_json  TEXT NOT NULL,
                model         TEXT NOT NULL,
                options_json  TEXT NOT NULL,
                eval_count    INTEGER,
                done_reason   TEXT,
                error_message TEXT
            )
        """)
        )
        conn.execute(sa.text("CREATE INDEX idx_qa_history_asked_at ON qa_history(asked_at DESC)"))

    if "book_characters" not in existing:
        conn.execute(
            sa.text("""
            CREATE TABLE book_characters (
                id           INTEGER PRIMARY KEY,
                book_id      INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                name         TEXT NOT NULL,
                summary      TEXT,
                first_page   INTEGER NOT NULL,
                page_count   INTEGER NOT NULL,
                generated_at TIMESTAMP,
                UNIQUE(book_id, name)
            )
        """)
        )
        conn.execute(sa.text("CREATE INDEX idx_book_characters_book ON book_characters(book_id)"))

    if "qa_sessions" not in existing:
        conn.execute(
            sa.text("""
            CREATE TABLE qa_sessions (
                id              INTEGER PRIMARY KEY,
                scope_type      TEXT NOT NULL,
                scope_id        TEXT,
                title           TEXT,
                started_at      TIMESTAMP DEFAULT (datetime('now', '+9 hours')),
                last_message_at TIMESTAMP
            )
        """)
        )
        conn.execute(sa.text("CREATE INDEX idx_qa_sessions_started ON qa_sessions(started_at DESC)"))

    if "qa_messages" not in existing:
        conn.execute(
            sa.text("""
            CREATE TABLE qa_messages (
                id          INTEGER PRIMARY KEY,
                session_id  INTEGER NOT NULL REFERENCES qa_sessions(id) ON DELETE CASCADE,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                eval_count  INTEGER,
                done_reason TEXT,
                created_at  TIMESTAMP DEFAULT (datetime('now', '+9 hours'))
            )
        """)
        )
        conn.execute(sa.text("CREATE INDEX idx_qa_messages_session ON qa_messages(session_id, id)"))

    if "rebuild_jobs" not in existing:
        conn.execute(
            sa.text("""
            CREATE TABLE rebuild_jobs (
                id              INTEGER PRIMARY KEY,
                job_type        TEXT NOT NULL,
                target_id       TEXT,
                mode            TEXT NOT NULL DEFAULT 'rebuild',
                state           TEXT NOT NULL DEFAULT 'queued',
                enqueued_at     TIMESTAMP DEFAULT (datetime('now', '+9 hours')),
                started_at      TIMESTAMP,
                finished_at     TIMESTAMP,
                progress_total  INTEGER,
                progress_done   INTEGER,
                error_message   TEXT,
                current_step    TEXT,
                current_detail  TEXT
            )
        """)
        )
        conn.execute(sa.text("CREATE INDEX idx_rebuild_jobs_state ON rebuild_jobs(state, enqueued_at)"))


def downgrade() -> None:
    pass  # intentionally no-op
