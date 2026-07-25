"""add capture job heartbeat

Revision ID: 8f4c1b0a2d3e
Revises: 2344a4d50919
Create Date: 2026-07-25 21:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

revision: str = "8f4c1b0a2d3e"
down_revision: str | Sequence[str] | None = "2344a4d50919"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "capture_jobs",
        sa.Column(
            "heartbeat_at",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_capture_jobs_heartbeat_at"),
        "capture_jobs",
        ["heartbeat_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_capture_jobs_heartbeat_at"), table_name="capture_jobs")
    op.drop_column("capture_jobs", "heartbeat_at")
