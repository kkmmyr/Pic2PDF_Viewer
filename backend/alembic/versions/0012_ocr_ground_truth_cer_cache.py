"""0012: cache API CER inputs and page metrics

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-17
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ocr_ground_truth_pages") as batch_op:
        batch_op.add_column(sa.Column("cer_reference_sha256", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("cer_hypothesis_sha256", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("cer_edit_distance", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("cer_reference_chars", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ocr_ground_truth_pages") as batch_op:
        batch_op.drop_column("cer_reference_chars")
        batch_op.drop_column("cer_edit_distance")
        batch_op.drop_column("cer_hypothesis_sha256")
        batch_op.drop_column("cer_reference_sha256")
