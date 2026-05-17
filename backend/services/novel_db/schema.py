"""novel.db のスキーマ DDL と初期化関数。

詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §4。
"""
import sqlite3


def _ddl() -> str:
    return """
        CREATE TABLE IF NOT EXISTS books (
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
        );
        CREATE INDEX IF NOT EXISTS idx_books_name ON books(name);

        CREATE TABLE IF NOT EXISTS pages (
            id              INTEGER PRIMARY KEY,
            book_id         INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            page_no         INTEGER NOT NULL,
            image_path      TEXT,
            full_text       TEXT,
            char_count      INTEGER NOT NULL,
            main_characters TEXT,
            UNIQUE(book_id, page_no)
        );
        CREATE INDEX IF NOT EXISTS idx_pages_book ON pages(book_id);

        CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
            full_text,
            content='pages',
            content_rowid='id',
            tokenize='trigram'
        );

        CREATE TABLE IF NOT EXISTS chunks (
            id                     INTEGER PRIMARY KEY,
            page_id                INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            chunk_idx              INTEGER NOT NULL,
            text                   TEXT NOT NULL,
            char_count             INTEGER NOT NULL,
            contextual_text        TEXT,
            contextual_generated_at TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_chunks_page ON chunks(page_id);

        CREATE TABLE IF NOT EXISTS qa_history (
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
        );
        CREATE INDEX IF NOT EXISTS idx_qa_history_asked_at ON qa_history(asked_at DESC);

        CREATE TABLE IF NOT EXISTS book_characters (
            id              INTEGER PRIMARY KEY,
            book_id         INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            name            TEXT NOT NULL,
            summary         TEXT,
            first_page      INTEGER NOT NULL,
            page_count      INTEGER NOT NULL,
            generated_at    TIMESTAMP,
            UNIQUE(book_id, name)
        );
        CREATE INDEX IF NOT EXISTS idx_book_characters_book ON book_characters(book_id);

        CREATE TABLE IF NOT EXISTS qa_sessions (
            id              INTEGER PRIMARY KEY,
            scope_type      TEXT NOT NULL,
            scope_id        TEXT,
            title           TEXT,
            started_at      TIMESTAMP DEFAULT (datetime('now', '+9 hours')),
            last_message_at TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_qa_sessions_started ON qa_sessions(started_at DESC);

        CREATE TABLE IF NOT EXISTS qa_messages (
            id           INTEGER PRIMARY KEY,
            session_id   INTEGER NOT NULL REFERENCES qa_sessions(id) ON DELETE CASCADE,
            role         TEXT NOT NULL,
            content      TEXT NOT NULL,
            eval_count   INTEGER,
            done_reason  TEXT,
            created_at   TIMESTAMP DEFAULT (datetime('now', '+9 hours'))
        );
        CREATE INDEX IF NOT EXISTS idx_qa_messages_session ON qa_messages(session_id, id);

        CREATE TABLE IF NOT EXISTS rebuild_jobs (
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
        );
        CREATE INDEX IF NOT EXISTS idx_rebuild_jobs_state ON rebuild_jobs(state, enqueued_at);

        CREATE TABLE IF NOT EXISTS character_relations (
            id            INTEGER PRIMARY KEY,
            series_id     TEXT    NOT NULL,
            book_id       INTEGER NOT NULL,
            char_a        TEXT    NOT NULL,
            char_b        TEXT    NOT NULL,
            relation_type TEXT,
            weight        REAL    NOT NULL DEFAULT 1.0,
            generated_at  TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_char_relations_series ON character_relations(series_id);
        CREATE INDEX IF NOT EXISTS idx_char_relations_book ON character_relations(book_id);
    """


def init_schema(conn: sqlite3.Connection) -> None:
    """全テーブルを冪等に作成する。カラム追加マイグレーションは Alembic (upgrade_head) が担う。"""
    conn.executescript(_ddl())
    conn.commit()
