"""Kindle カタログ DB の Alembic upgrade ヘルパー。"""

from pathlib import Path

from alembic.config import Config

from alembic import command

_ALEMBIC_INI = Path(__file__).parent.parent.parent / "alembic_kindle.ini"


def upgrade_head() -> None:
    cfg = Config(str(_ALEMBIC_INI))
    command.upgrade(cfg, "head")
