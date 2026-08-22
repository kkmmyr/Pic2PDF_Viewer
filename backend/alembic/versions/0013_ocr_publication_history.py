"""0013: preserve materialized OCR text and publication history

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-19
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ocr_page_results") as batch_op:
        batch_op.add_column(sa.Column("published_text", sa.Text(), nullable=True))

    op.create_table(
        "ocr_publications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_id", sa.Integer(), sa.ForeignKey("books.id"), nullable=False),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("ocr_runs.id"), nullable=False),
        sa.Column(
            "superseded_publication_id",
            sa.Integer(),
            sa.ForeignKey("ocr_publications.id"),
            nullable=True,
        ),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("published_at", sa.Text(), nullable=False),
        sa.Column("retired_at", sa.Text(), nullable=True),
    )
    op.create_index("idx_ocr_publications_book", "ocr_publications", ["book_id", "published_at"])
    op.create_index(
        "uq_ocr_publications_active_book",
        "ocr_publications",
        ["book_id"],
        unique=True,
        sqlite_where=sa.text("retired_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_ocr_publications_active_book", table_name="ocr_publications")
    op.drop_index("idx_ocr_publications_book", table_name="ocr_publications")
    op.drop_table("ocr_publications")
    with op.batch_alter_table("ocr_page_results") as batch_op:
        batch_op.drop_column("published_text")
