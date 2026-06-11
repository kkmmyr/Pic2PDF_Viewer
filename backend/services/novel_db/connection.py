"""novel.db の接続ヘルパー（foreign keys 有効化）。"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import config


def _ensure_dir() -> None:
    Path(config.NOVEL_DB_DIR).mkdir(parents=True, exist_ok=True)


def open_db(db_path: str | None = None) -> sqlite3.Connection:
    """sqlite3 接続を開いて返す。

    呼び出し元が close() の責務を持つ。短命用途では with_db() を推奨。
    row_factory = sqlite3.Row を設定するのでカラム名でのアクセスと
    model_validate(dict(row)) によるモデル変換が使用できる。
    """
    _ensure_dir()
    conn = sqlite3.connect(db_path or config.NOVEL_DB_PATH, timeout=30)
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
