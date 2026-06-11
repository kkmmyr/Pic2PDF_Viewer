"""novel.db の接続ヘルパー（foreign keys 有効化）。"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from config import app_settings


def _ensure_dir() -> None:
    app_settings.NOVEL_DB_DIR.mkdir(parents=True, exist_ok=True)


def open_db(db_path: str | None = None) -> sqlite3.Connection:
    """sqlite3 接続を開いて返す。

    呼び出し元が close() の責務を持つ。短命用途では with_db() を推奨。
    row_factory = sqlite3.Row を設定するのでカラム名でのアクセスと
    model_validate(dict(row)) によるモデル変換が使用できる。
    """
    _ensure_dir()
    conn = sqlite3.connect(db_path or str(app_settings.NOVEL_DB_DIR / "novel.db"), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def with_db(db_path: str | None = None) -> Iterator[sqlite3.Connection]:
    """short-lived な DB アクセス向けの context manager。

    使用例:
        with with_db() as conn:
            cur = conn.execute("SELECT ...")
            ...
    """
    conn = open_db(db_path)
    try:
        yield conn
    finally:
        conn.close()
