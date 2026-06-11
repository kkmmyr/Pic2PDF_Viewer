"""Alembic 実行環境設定。

sqlite3 runtime のまま novel.db のみを管理する。
SQLModel.metadata を target_metadata に設定し autogenerate に対応。
pages_fts（FTS5 仮想テーブル）は include_name フィルタで除外。
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
from services.novel_db.models import SQLModel  # noqa: E402

alembic_config = context.config

if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

# SQLModel.metadata を使用 → alembic revision --autogenerate でスキーマ差分を検出できる
target_metadata = SQLModel.metadata


def include_name(name: str, type_: str, parent_names: dict) -> bool:
    """pages_fts（FTS5 仮想テーブル）を autogenerate 対象から除外する。"""
    if type_ == "table":
        return name not in {"pages_fts"}
    return True


def _db_url() -> str:
    return "sqlite:///" + config.NOVEL_DB_PATH.replace("\\", "/")


def run_migrations_offline() -> None:
    context.configure(
        url=_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    Path(config.NOVEL_DB_DIR).mkdir(parents=True, exist_ok=True)
    engine = create_engine(_db_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_name=include_name,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
