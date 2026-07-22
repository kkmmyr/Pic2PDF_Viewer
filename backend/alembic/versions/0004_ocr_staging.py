"""0004: add page-level OCR staging tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-19
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ocr_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_name", sa.Text(), nullable=False),
        sa.Column("engine", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("source_page_count", sa.Integer(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="running"),
        sa.Column("started_at", sa.Text(), server_default=sa.text("(datetime('now', '+9 hours'))")),
        sa.Column("finished_at", sa.Text()),
        sa.Column("error_message", sa.Text()),
    )
    op.create_index("idx_ocr_runs_book_state", "ocr_runs", ["book_name", "state"])

    op.create_table(
        "ocr_page_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("ocr_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("image_sha256", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("full_text", sa.Text()),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_output", sa.Text()),
        sa.Column("block_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quality_flags_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("ink_coverage", sa.Float()),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column("updated_at", sa.Text(), server_default=sa.text("(datetime('now', '+9 hours'))")),
        sa.UniqueConstraint("run_id", "page_no"),
    )
    op.create_index("idx_ocr_page_results_run_state", "ocr_page_results", ["run_id", "state"])


def downgrade() -> None:
    op.drop_index("idx_ocr_page_results_run_state", table_name="ocr_page_results")
    op.drop_table("ocr_page_results")
    op.drop_index("idx_ocr_runs_book_state", table_name="ocr_runs")
    op.drop_table("ocr_runs")
