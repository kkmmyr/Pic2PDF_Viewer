"""0007: add OCR page types and ground-truth corpus

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("pages") as batch:
        batch.add_column(sa.Column("page_type", sa.Text(), nullable=False, server_default="narrative"))
        batch.add_column(sa.Column("index_eligible", sa.Boolean(), nullable=False, server_default=sa.true()))

    with op.batch_alter_table("ocr_page_results") as batch:
        batch.add_column(sa.Column("page_type", sa.Text(), nullable=False, server_default="unknown"))
        batch.add_column(sa.Column("index_eligible", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        "ocr_ground_truth_pages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("ocr_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("image_sha256", sa.Text(), nullable=False),
        sa.Column("page_type", sa.Text(), nullable=False, server_default="unknown"),
        sa.Column("reference_text", sa.Text()),
        sa.Column("state", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.Text()),
        sa.Column("updated_at", sa.Text()),
        sa.Column("verified_at", sa.Text()),
        sa.UniqueConstraint("run_id", "page_no"),
    )
    op.create_index(
        "idx_ocr_ground_truth_state",
        "ocr_ground_truth_pages",
        ["state", "run_id", "page_no"],
    )


def downgrade() -> None:
    op.drop_index("idx_ocr_ground_truth_state", table_name="ocr_ground_truth_pages")
    op.drop_table("ocr_ground_truth_pages")
    with op.batch_alter_table("ocr_page_results") as batch:
        batch.drop_column("index_eligible")
        batch.drop_column("page_type")
    with op.batch_alter_table("pages") as batch:
        batch.drop_column("index_eligible")
        batch.drop_column("page_type")
