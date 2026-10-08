"""allow pending Kindle price notifications

Revision ID: e7b2c4d91f30
Revises: c4f9d2a6e8b1
Create Date: 2026-10-08 08:10:00.000000
"""

from collections.abc import Sequence

from sqlmodel.sql.sqltypes import AutoString

from alembic import op

revision: str = "e7b2c4d91f30"
down_revision: str | Sequence[str] | None = "c4f9d2a6e8b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("kindle_price_notifications") as batch_op:
        batch_op.alter_column("notified_at", existing_type=AutoString(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM kindle_price_notifications WHERE notified_at IS NULL")
    with op.batch_alter_table("kindle_price_notifications") as batch_op:
        batch_op.alter_column("notified_at", existing_type=AutoString(), nullable=False)
