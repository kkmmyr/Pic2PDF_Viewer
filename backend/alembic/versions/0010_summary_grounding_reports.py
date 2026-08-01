"""0010: add summary grounding audit reports

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-01
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "summary_grounding_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "book_id",
            sa.Integer(),
            sa.ForeignKey("books.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("candidate_sha256", sa.Text(), nullable=False),
        sa.Column("writer_model", sa.Text(), nullable=False),
        sa.Column("verifier_model", sa.Text(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("report_json", sa.Text(), nullable=False),
        sa.Column(
            "checked_at",
            sa.Text(),
            server_default=sa.text("(datetime('now', '+9 hours'))"),
        ),
    )
    op.create_index(
        "idx_summary_grounding_reports_book",
        "summary_grounding_reports",
        ["book_id", "checked_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_summary_grounding_reports_book", table_name="summary_grounding_reports")
    op.drop_table("summary_grounding_reports")
