"""0009: add fact extraction block checkpoints

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-01
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fact_extraction_blocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "book_id",
            sa.Integer(),
            sa.ForeignKey("books.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("block_index", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("source_hash", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("book_facts", sa.Text(), nullable=False),
        sa.Column("character_facts_json", sa.Text(), nullable=False),
        sa.Column("fact_records_json", sa.Text(), nullable=False),
        sa.Column(
            "generated_at",
            sa.Text(),
            server_default=sa.text("(datetime('now', '+9 hours'))"),
        ),
        sa.UniqueConstraint("book_id", "block_index"),
    )
    op.create_index(
        "idx_fact_extraction_blocks_book",
        "fact_extraction_blocks",
        ["book_id", "block_index"],
    )


def downgrade() -> None:
    op.drop_index("idx_fact_extraction_blocks_book", table_name="fact_extraction_blocks")
    op.drop_table("fact_extraction_blocks")
