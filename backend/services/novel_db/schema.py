"""novel.db のスキーマ DDL と初期化関数。

詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §4。
"""
import sqlite3

from config import NOVEL_DB_EMBED_DIM


def _ddl() -> str:
    return f"""
        CREATE TABLE IF NOT EXISTS books (
            id          INTEGER PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            pdf_path    TEXT NOT NULL,
            images_dir  TEXT NOT NULL,
            page_count  INTEGER NOT NULL,
            indexed_at  TIMESTAMP NOT NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_books_name ON books(name);

        CREATE TABLE IF NOT EXISTS pages (
            id         INTEGER PRIMARY KEY,
            book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            page_no    INTEGER NOT NULL,
            image_path TEXT,
            full_text  TEXT,
            char_count INTEGER NOT NULL,
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
            id         INTEGER PRIMARY KEY,
            page_id    INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            chunk_idx  INTEGER NOT NULL,
            text       TEXT NOT NULL,
            char_count INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_chunks_page ON chunks(page_id);

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(embedding FLOAT[{NOVEL_DB_EMBED_DIM}]);

        -- 書籍サマリ（books.summary）の embedding。
        -- rowid = books.id。scope=all / scope=series の RAG で「サマリ自体が
        -- ヒット候補」になるよう、bge-m3 で書籍 1 冊あたり 1 ベクトルを格納する。
        -- B-5 の summary 生成完了時に upsert する。
        CREATE VIRTUAL TABLE IF NOT EXISTS book_summaries_vec USING vec0(embedding FLOAT[{NOVEL_DB_EMBED_DIM}]);

        CREATE TABLE IF NOT EXISTS qa_history (
            id            INTEGER PRIMARY KEY,
            asked_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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

        -- B-15: キャラクター辞典。書籍ごとのキャラ単位サマリ + 登場ページ統計。
        -- main_characters カラム集計から生成、Qwen でキャラ視点の 1 段落要約を作る。
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

        -- B-16: マルチターン会話 QA。1 セッションは scope 固定、ターンごとに
        -- qa_messages へ user / assistant メッセージを追記する。既存 qa_history
        -- は単発 QA 用に温存（B-16 では非利用）。
        CREATE TABLE IF NOT EXISTS qa_sessions (
            id              INTEGER PRIMARY KEY,
            scope_type      TEXT NOT NULL,
            scope_id        TEXT,
            title           TEXT,
            started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_message_at TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_qa_sessions_started ON qa_sessions(started_at DESC);

        CREATE TABLE IF NOT EXISTS qa_messages (
            id           INTEGER PRIMARY KEY,
            session_id   INTEGER NOT NULL REFERENCES qa_sessions(id) ON DELETE CASCADE,
            role         TEXT NOT NULL,           -- 'user' / 'assistant' / 'system'
            content      TEXT NOT NULL,
            eval_count   INTEGER,                 -- assistant のみ。NULL 可
            done_reason  TEXT,                    -- assistant のみ。'stop' / 'length' / 'canceled' / 'error'
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_qa_messages_session ON qa_messages(session_id, id);

        CREATE TABLE IF NOT EXISTS rebuild_jobs (
            id              INTEGER PRIMARY KEY,
            job_type        TEXT NOT NULL,
            target_id       TEXT,
            mode            TEXT NOT NULL DEFAULT 'pdf_text',
            state           TEXT NOT NULL DEFAULT 'queued',
            enqueued_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at      TIMESTAMP,
            finished_at     TIMESTAMP,
            progress_total  INTEGER,
            progress_done   INTEGER,
            error_message   TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_rebuild_jobs_state ON rebuild_jobs(state, enqueued_at);
    """


def init_schema(conn: sqlite3.Connection) -> None:
    """全テーブルを冪等に作成し、必要なら既存 DB をマイグレートする。"""
    conn.executescript(_ddl())
    _migrate(conn)
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    """既存 DB に対する追加カラム等のマイグレーション（冪等）。"""
    pages_cols = {row[1] for row in conn.execute("PRAGMA table_info(pages)").fetchall()}
    if "main_characters" not in pages_cols:
        # カンマ区切りの主要登場人物（character_extractor で生成）。
        # NULL = 未抽出、空文字 = 抽出済みだが該当なし。
        conn.execute("ALTER TABLE pages ADD COLUMN main_characters TEXT")

    books_cols = {row[1] for row in conn.execute("PRAGMA table_info(books)").fetchall()}
    if "summary" not in books_cols:
        # 書籍 1 冊あたり 1000〜1500 字程度のあらすじ（summarizer で生成）。
        # NULL = 未生成、空文字 = 生成試行したが失敗。
        # scope=all / scope=series の質問応答時にプロンプト先頭へ付与する。
        conn.execute("ALTER TABLE books ADD COLUMN summary TEXT")
    if "summary_generated_at" not in books_cols:
        conn.execute("ALTER TABLE books ADD COLUMN summary_generated_at TIMESTAMP")

    chunks_cols = {row[1] for row in conn.execute("PRAGMA table_info(chunks)").fetchall()}
    if "contextual_text" not in chunks_cols:
        # B-9 Contextual Retrieval: チャンクごとの「位置説明」（80 字程度）。
        # contextualizer.py が gemma4:e4b で生成。NULL = 未生成。
        # chunks_vec の embedding は (contextual_text + text) で再計算する。
        conn.execute("ALTER TABLE chunks ADD COLUMN contextual_text TEXT")
    if "contextual_generated_at" not in chunks_cols:
        conn.execute("ALTER TABLE chunks ADD COLUMN contextual_generated_at TIMESTAMP")
