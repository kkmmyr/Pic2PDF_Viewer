"""Alembic 実行環境設定。

sqlite3 runtime のまま novel.db のみを管理する。
autogenerate 不使用・手書き revision のみ・downgrade は pass。
"""
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import create_engine, pool

from alembic import context

# backend/ をパスに追加して config モジュールを import できるようにする
sys.path.insert(0, str(Path(__file__).parent.parent))
import config  # noqa: E402

alembic_config = context.config

if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

target_metadata = None  # autogenerate 不使用


def _db_url() -> str:
    return "sqlite:///" + config.NOVEL_DB_PATH.replace("\\", "/")


def run_migrations_offline() -> None:
    context.configure(url=_db_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    Path(config.NOVEL_DB_DIR).mkdir(parents=True, exist_ok=True)
    engine = create_engine(_db_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
