"""0014: add generation state for external novel search indexes

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    state_table = op.create_table(
        "novel_search_index_state",
        sa.Column("index_name", sa.Text(), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_source_revision", sa.Integer(), nullable=True),
        sa.Column("active_table_name", sa.Text(), nullable=True),
        sa.Column("source_sha256", sa.Text(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="missing"),
        sa.Column("built_at", sa.Text(), nullable=True),
        sa.Column("lancedb_version", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("index_name"),
        sa.CheckConstraint(
            "status IN ('missing', 'stale', 'active')",
            name="ck_novel_search_index_state_status",
        ),
    )
    op.bulk_insert(
        state_table,
        [
            {
                "index_name": "page_icu",
                "source_revision": 0,
                "status": "missing",
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("novel_search_index_state")
