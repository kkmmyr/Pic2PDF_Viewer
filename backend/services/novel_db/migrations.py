"""novel.db Alembic マイグレーション実行ヘルパー。

起動時に upgrade_head() を呼ぶことで novel.db を最新 revision に追従させる。
失敗時は例外を送出し FastAPI の起動を中断する。
"""
from __future__ import annotations

from pathlib import Path

from alembic.config import Config

from alembic import command
from config import NOVEL_DB_DIR

_ALEMBIC_INI = Path(__file__).parent.parent.parent / "alembic.ini"


def upgrade_head() -> None:
    """alembic upgrade head を実行する。失敗時は例外を送出し起動を中断する。"""
    Path(NOVEL_DB_DIR).mkdir(parents=True, exist_ok=True)
    cfg = Config(str(_ALEMBIC_INI))
    command.upgrade(cfg, "head")
