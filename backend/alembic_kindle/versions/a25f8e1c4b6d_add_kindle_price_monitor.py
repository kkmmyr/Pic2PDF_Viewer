"""add Codex browser Kindle price monitoring tables

Revision ID: a25f8e1c4b6d
Revises: d1a4c7e92b6f
Create Date: 2026-08-23 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlmodel.sql.sqltypes import AutoString

from alembic import op

revision: str = "a25f8e1c4b6d"
down_revision: str | Sequence[str] | None = "d1a4c7e92b6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "kindle_price_watches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("url", AutoString(length=500), nullable=False),
        sa.Column("asin", AutoString(length=20), nullable=True),
        sa.Column("title", AutoString(), nullable=True),
        sa.Column("threshold_percent", sa.Float(), nullable=False),
        sa.Column("notify_on_drop", sa.Boolean(), nullable=False),
        sa.Column("notify_below_threshold", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", AutoString(), nullable=False),
        sa.Column("updated_at", AutoString(), nullable=False),
        sa.Column("last_checked_at", AutoString(), nullable=True),
        sa.Column("last_status", AutoString(), nullable=False),
        sa.Column("last_error", AutoString(), nullable=True),
        sa.Column("last_current_price", sa.Integer(), nullable=True),
        sa.Column("last_list_price", sa.Integer(), nullable=True),
        sa.Column("last_ratio_percent", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
    )
    op.create_index("ix_kindle_price_watches_asin", "kindle_price_watches", ["asin"])
    op.create_index("ix_kindle_price_watches_enabled", "kindle_price_watches", ["enabled"])
    op.create_index("ix_kindle_price_watches_last_status", "kindle_price_watches", ["last_status"])
    op.create_index("ix_kindle_price_watches_url", "kindle_price_watches", ["url"])

    op.create_table(
        "kindle_price_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("watch_id", sa.Integer(), nullable=False),
        sa.Column("observed_at", AutoString(), nullable=False),
        sa.Column("current_price", sa.Integer(), nullable=True),
        sa.Column("list_price", sa.Integer(), nullable=True),
        sa.Column("ratio_percent", sa.Float(), nullable=True),
        sa.Column("status", AutoString(), nullable=False),
        sa.Column("error_message", AutoString(), nullable=True),
        sa.Column("source", AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["watch_id"], ["kindle_price_watches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kindle_price_observations_watch_id", "kindle_price_observations", ["watch_id"])
    op.create_index("ix_kindle_price_observations_observed_at", "kindle_price_observations", ["observed_at"])
    op.create_index("ix_kindle_price_observations_status", "kindle_price_observations", ["status"])
    op.create_index("ix_kindle_price_observations_source", "kindle_price_observations", ["source"])

    op.create_table(
        "kindle_price_notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("watch_id", sa.Integer(), nullable=False),
        sa.Column("observation_id", sa.Integer(), nullable=False),
        sa.Column("kind", AutoString(), nullable=False),
        sa.Column("notified_at", AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["watch_id"], ["kindle_price_watches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["observation_id"], ["kindle_price_observations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("observation_id", "kind"),
    )
    op.create_index("ix_kindle_price_notifications_watch_id", "kindle_price_notifications", ["watch_id"])
    op.create_index("ix_kindle_price_notifications_observation_id", "kindle_price_notifications", ["observation_id"])
    op.create_index("ix_kindle_price_notifications_kind", "kindle_price_notifications", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_kindle_price_notifications_kind", table_name="kindle_price_notifications")
    op.drop_index("ix_kindle_price_notifications_observation_id", table_name="kindle_price_notifications")
    op.drop_index("ix_kindle_price_notifications_watch_id", table_name="kindle_price_notifications")
    op.drop_table("kindle_price_notifications")

    op.drop_index("ix_kindle_price_observations_source", table_name="kindle_price_observations")
    op.drop_index("ix_kindle_price_observations_status", table_name="kindle_price_observations")
    op.drop_index("ix_kindle_price_observations_observed_at", table_name="kindle_price_observations")
    op.drop_index("ix_kindle_price_observations_watch_id", table_name="kindle_price_observations")
    op.drop_table("kindle_price_observations")

    op.drop_index("ix_kindle_price_watches_url", table_name="kindle_price_watches")
    op.drop_index("ix_kindle_price_watches_last_status", table_name="kindle_price_watches")
    op.drop_index("ix_kindle_price_watches_enabled", table_name="kindle_price_watches")
    op.drop_index("ix_kindle_price_watches_asin", table_name="kindle_price_watches")
    op.drop_table("kindle_price_watches")
