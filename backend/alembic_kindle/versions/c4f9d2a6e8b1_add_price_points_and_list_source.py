"""add Kindle price points, effective price, and list price source

Revision ID: c4f9d2a6e8b1
Revises: a25f8e1c4b6d
Create Date: 2026-10-05 05:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlmodel.sql.sqltypes import AutoString

from alembic import op

revision: str = "c4f9d2a6e8b1"
down_revision: str | Sequence[str] | None = "a25f8e1c4b6d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("kindle_price_watches", sa.Column("last_points", sa.Integer(), nullable=True))
    op.add_column("kindle_price_watches", sa.Column("last_effective_price", sa.Integer(), nullable=True))
    op.add_column("kindle_price_watches", sa.Column("last_list_price_source", AutoString(), nullable=True))
    op.add_column("kindle_price_observations", sa.Column("points", sa.Integer(), nullable=True))
    op.add_column("kindle_price_observations", sa.Column("effective_price", sa.Integer(), nullable=True))
    op.add_column("kindle_price_observations", sa.Column("list_price_source", AutoString(), nullable=True))


def downgrade() -> None:
    op.drop_column("kindle_price_observations", "list_price_source")
    op.drop_column("kindle_price_observations", "effective_price")
    op.drop_column("kindle_price_observations", "points")
    op.drop_column("kindle_price_watches", "last_list_price_source")
    op.drop_column("kindle_price_watches", "last_effective_price")
    op.drop_column("kindle_price_watches", "last_points")
