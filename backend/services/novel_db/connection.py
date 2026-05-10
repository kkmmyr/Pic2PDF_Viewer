"""novel.db の接続ヘルパー（sqlite_vec ロード + foreign keys 有効化）。"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import sqlite_vec

from config import NOVEL_DB_DIR, NOVEL_DB_PATH


def _ensure_dir() -> None:
    Path(NOVEL_DB_DIR).mkdir(parents=True, exist_ok=True)


def open_db(db_path: str | None = None) -> sqlite3.Connection:
    """sqlite3 接続を開き、sqlite_vec を有効化して返す。

    呼び出し元が close() の責務を持つ。短命用途では with_db() を推奨。
    """
    _ensure_dir()
    conn = sqlite3.connect(db_path or NOVEL_DB_PATH)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
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
