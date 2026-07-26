"""0005: add OCR QA approval state

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ocr_runs") as batch:
        batch.add_column(sa.Column("qa_state", sa.Text(), nullable=False, server_default="pending"))
        batch.add_column(sa.Column("qa_reviewer", sa.Text()))
        batch.add_column(sa.Column("qa_reviewed_at", sa.Text()))
        batch.add_column(sa.Column("qa_note", sa.Text()))

    with op.batch_alter_table("ocr_page_results") as batch:
        batch.add_column(sa.Column("qa_state", sa.Text(), nullable=False, server_default="not_required"))
        batch.add_column(sa.Column("qa_note", sa.Text()))
        batch.add_column(sa.Column("reviewed_at", sa.Text()))
    op.create_index("idx_ocr_page_results_run_qa", "ocr_page_results", ["run_id", "qa_state"])


def downgrade() -> None:
    op.drop_index("idx_ocr_page_results_run_qa", table_name="ocr_page_results")
    with op.batch_alter_table("ocr_page_results") as batch:
        batch.drop_column("reviewed_at")
        batch.drop_column("qa_note")
        batch.drop_column("qa_state")
    with op.batch_alter_table("ocr_runs") as batch:
        batch.drop_column("qa_note")
        batch.drop_column("qa_reviewed_at")
        batch.drop_column("qa_reviewer")
        batch.drop_column("qa_state")
