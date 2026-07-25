"""Kindle カタログ DB の短命 sqlite3 接続。"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import config


def db_path() -> Path:
    """テストで差し替え可能なモジュール設定から DB パスを解決する。"""
    return Path(config.META_DB_DIR) / "kindle_catalog.db"


def open_db(path: Path | str | None = None) -> sqlite3.Connection:
    target = Path(path) if path is not None else db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


@contextmanager
def with_db(path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    conn = open_db(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
