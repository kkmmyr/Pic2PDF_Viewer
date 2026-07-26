"""0008: add OCR layout candidates and reviewed corrections

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ocr_page_results") as batch:
        batch.add_column(sa.Column("layout_type", sa.Text(), nullable=False, server_default="unknown"))
        batch.add_column(sa.Column("primary_text", sa.Text()))
        batch.add_column(sa.Column("external_text", sa.Text()))
        batch.add_column(sa.Column("selected_engine", sa.Text(), nullable=False, server_default="primary"))
        batch.add_column(sa.Column("corrected_text", sa.Text()))

    with op.batch_alter_table("ocr_ground_truth_pages") as batch:
        batch.add_column(sa.Column("layout_type", sa.Text(), nullable=False, server_default="unknown"))


def downgrade() -> None:
    with op.batch_alter_table("ocr_ground_truth_pages") as batch:
        batch.drop_column("layout_type")
    with op.batch_alter_table("ocr_page_results") as batch:
        batch.drop_column("corrected_text")
        batch.drop_column("selected_engine")
        batch.drop_column("external_text")
        batch.drop_column("primary_text")
        batch.drop_column("layout_type")
