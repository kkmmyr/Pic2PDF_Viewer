"""C-12: character_relations テーブル追加

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-17
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    tables = {row[0] for row in conn.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()}
    if "character_relations" in tables:
        return
    conn.execute(
        sa.text("""
        CREATE TABLE character_relations (
            id            INTEGER PRIMARY KEY,
            series_id     TEXT    NOT NULL,
            book_id       INTEGER NOT NULL,
            char_a        TEXT    NOT NULL,
            char_b        TEXT    NOT NULL,
            relation_type TEXT,
            weight        REAL    NOT NULL DEFAULT 1.0,
            generated_at  TEXT    NOT NULL
        )
    """)
    )
    conn.execute(sa.text("CREATE INDEX idx_char_relations_series ON character_relations(series_id)"))
    conn.execute(sa.text("CREATE INDEX idx_char_relations_book ON character_relations(book_id)"))


def downgrade() -> None:
    op.drop_table("character_relations")
