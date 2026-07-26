"""0006: add Windows OCR agent job ownership

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("rebuild_jobs") as batch:
        batch.add_column(sa.Column("agent_id", sa.Text()))
        batch.add_column(sa.Column("heartbeat_at", sa.Text()))
    op.create_index("idx_rebuild_jobs_agent", "rebuild_jobs", ["mode", "state", "agent_id"])

    op.create_table(
        "ocr_agent_job_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("rebuild_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("ocr_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("book_name", sa.Text(), nullable=False),
        sa.UniqueConstraint("job_id", "book_name"),
        sa.UniqueConstraint("job_id", "run_id"),
    )


def downgrade() -> None:
    op.drop_table("ocr_agent_job_runs")
    op.drop_index("idx_rebuild_jobs_agent", table_name="rebuild_jobs")
    with op.batch_alter_table("rebuild_jobs") as batch:
        batch.drop_column("heartbeat_at")
        batch.drop_column("agent_id")
