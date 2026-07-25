"""Kindle カタログ専用 Alembic 環境。"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import create_engine, event, pool

from alembic import context

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.kindle_catalog.connection import db_path
from services.kindle_catalog.models import KindleSQLModel

alembic_config = context.config
if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

target_metadata = KindleSQLModel.metadata


def _db_url() -> str:
    return "sqlite:///" + str(db_path()).replace("\\", "/")


def run_migrations_offline() -> None:
    context.configure(url=_db_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    db_path().parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(_db_url(), poolclass=pool.NullPool)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
