"""add capture quality warning audits

Revision ID: d1a4c7e92b6f
Revises: 8f4c1b0a2d3e
Create Date: 2026-08-22 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlmodel.sql.sqltypes import AutoString

from alembic import op

revision: str = "d1a4c7e92b6f"
down_revision: str | Sequence[str] | None = "8f4c1b0a2d3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "capture_quality_audits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", AutoString(), nullable=False),
        sa.Column("asin", AutoString(), nullable=False),
        sa.Column("source", AutoString(), nullable=False),
        sa.Column("book_id", AutoString(), nullable=False),
        sa.Column("qa_policy_version", AutoString(), nullable=False),
        sa.Column("warning_policy_version", AutoString(), nullable=False),
        sa.Column("quality_sha256", AutoString(length=64), nullable=False),
        sa.Column("created_at", AutoString(), nullable=False),
        sa.Column("superseded_at", AutoString(), nullable=True),
        sa.Column("superseded_by_job_id", AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["asin"], ["books.asin"]),
        sa.ForeignKeyConstraint(["job_id"], ["capture_jobs.id"]),
        sa.ForeignKeyConstraint(["superseded_by_job_id"], ["capture_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index(
        "ix_capture_quality_audits_asin",
        "capture_quality_audits",
        ["asin"],
    )
    op.create_index(
        "ix_capture_quality_audits_book_id",
        "capture_quality_audits",
        ["book_id"],
    )
    op.create_index(
        "ix_capture_quality_audits_job_id",
        "capture_quality_audits",
        ["job_id"],
    )
    op.create_index(
        "ix_capture_quality_audits_source",
        "capture_quality_audits",
        ["source"],
    )
    op.create_index(
        "ix_capture_quality_audits_superseded_at",
        "capture_quality_audits",
        ["superseded_at"],
    )
    op.create_index(
        "uq_capture_quality_audits_active_book",
        "capture_quality_audits",
        ["source", "book_id"],
        unique=True,
        sqlite_where=sa.text("superseded_at IS NULL"),
    )
    op.create_table(
        "capture_quality_warnings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("audit_id", sa.Integer(), nullable=False),
        sa.Column("code", AutoString(), nullable=False),
        sa.Column("finding_count", sa.Integer(), nullable=False),
        sa.Column("files_json", AutoString(), nullable=False),
        sa.Column("findings_json", AutoString(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("read_at", AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["audit_id"], ["capture_quality_audits.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("audit_id", "code"),
    )
    op.create_index(
        "ix_capture_quality_warnings_audit_id",
        "capture_quality_warnings",
        ["audit_id"],
    )
    op.create_index(
        "ix_capture_quality_warnings_code",
        "capture_quality_warnings",
        ["code"],
    )
    op.create_index(
        "ix_capture_quality_warnings_is_read",
        "capture_quality_warnings",
        ["is_read"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_capture_quality_warnings_is_read",
        table_name="capture_quality_warnings",
    )
    op.drop_index(
        "ix_capture_quality_warnings_code",
        table_name="capture_quality_warnings",
    )
    op.drop_index(
        "ix_capture_quality_warnings_audit_id",
        table_name="capture_quality_warnings",
    )
    op.drop_table("capture_quality_warnings")
    op.drop_index(
        "uq_capture_quality_audits_active_book",
        table_name="capture_quality_audits",
    )
    op.drop_index(
        "ix_capture_quality_audits_superseded_at",
        table_name="capture_quality_audits",
    )
    op.drop_index(
        "ix_capture_quality_audits_source",
        table_name="capture_quality_audits",
    )
    op.drop_index(
        "ix_capture_quality_audits_job_id",
        table_name="capture_quality_audits",
    )
    op.drop_index(
        "ix_capture_quality_audits_book_id",
        table_name="capture_quality_audits",
    )
    op.drop_index(
        "ix_capture_quality_audits_asin",
        table_name="capture_quality_audits",
    )
    op.drop_table("capture_quality_audits")
