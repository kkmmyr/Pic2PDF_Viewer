"""0011: add a separately published catalog summary

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-01
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("books") as batch_op:
        batch_op.add_column(sa.Column("catalog_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("catalog_summary_generated_at", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("books") as batch_op:
        batch_op.drop_column("catalog_summary_generated_at")
        batch_op.drop_column("catalog_summary")
