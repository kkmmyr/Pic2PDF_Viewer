"""0015: add OCR runtime provenance, raw candidates, and phase timing

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-29
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ocr_runs") as batch:
        batch.add_column(sa.Column("runtime_manifest_json", sa.Text(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("timing_json", sa.Text(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("ocr_finished_at", sa.Text()))
        batch.add_column(sa.Column("qa_started_at", sa.Text()))
        batch.add_column(sa.Column("qa_finished_at", sa.Text()))

    with op.batch_alter_table("ocr_page_results") as batch:
        batch.add_column(sa.Column("primary_raw_output", sa.Text()))
        batch.add_column(sa.Column("external_raw_output", sa.Text()))
        batch.add_column(sa.Column("candidate_manifest_json", sa.Text(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("processing_timing_json", sa.Text(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("review_started_at", sa.Text()))
        batch.add_column(sa.Column("review_duration_ms", sa.Integer()))
        batch.add_column(sa.Column("correction_duration_ms", sa.Integer()))


def downgrade() -> None:
    with op.batch_alter_table("ocr_page_results") as batch:
        batch.drop_column("correction_duration_ms")
        batch.drop_column("review_duration_ms")
        batch.drop_column("review_started_at")
        batch.drop_column("processing_timing_json")
        batch.drop_column("candidate_manifest_json")
        batch.drop_column("external_raw_output")
        batch.drop_column("primary_raw_output")

    with op.batch_alter_table("ocr_runs") as batch:
        batch.drop_column("qa_finished_at")
        batch.drop_column("qa_started_at")
        batch.drop_column("ocr_finished_at")
        batch.drop_column("timing_json")
        batch.drop_column("runtime_manifest_json")
