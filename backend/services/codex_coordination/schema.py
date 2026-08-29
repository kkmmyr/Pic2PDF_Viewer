"""Codex端末間連携SQLiteの初期schema。"""

import sqlite3
from pathlib import Path


def initialize_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=5.0) as connection:
        _ = connection.execute("PRAGMA foreign_keys=ON")
        _ = connection.execute("PRAGMA busy_timeout=5000")
        _ = connection.execute("PRAGMA journal_mode=WAL")
        _ = connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS topics (
                id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('open', 'closed')),
                created_at TEXT NOT NULL,
                closed_at TEXT,
                closed_by TEXT,
                resolution TEXT
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                topic_id TEXT NOT NULL REFERENCES topics(id),
                sender TEXT NOT NULL,
                recipient TEXT NOT NULL,
                body TEXT NOT NULL,
                refs_json TEXT NOT NULL DEFAULT '{}',
                reply_to_id TEXT REFERENCES messages(id),
                status TEXT NOT NULL CHECK (status IN ('unread', 'acknowledged')),
                created_at TEXT NOT NULL,
                acknowledged_at TEXT,
                acknowledged_by TEXT,
                idempotency_key TEXT
            );

            CREATE UNIQUE INDEX IF NOT EXISTS uq_messages_sender_idempotency
            ON messages(sender, idempotency_key)
            WHERE idempotency_key IS NOT NULL;

            CREATE INDEX IF NOT EXISTS ix_messages_recipient_status_created
            ON messages(recipient, status, created_at DESC);

            CREATE INDEX IF NOT EXISTS ix_messages_topic_created
            ON messages(topic_id, created_at);

            CREATE TABLE IF NOT EXISTS comparison_contexts (
                comparison_group_id TEXT PRIMARY KEY,
                context_json TEXT NOT NULL,
                context_sha256 TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            PRAGMA user_version=1;
            """
        )
