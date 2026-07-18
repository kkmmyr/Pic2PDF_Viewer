"""meta2.db の接続・テーブル定義・JSON ファイルからの移行。

テスト時は monkeypatch.setattr(config, "META_DB_DIR", str(tmp_path)) でパスを切り替える。
"""

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

import config

_CREATE_DDL = """
CREATE TABLE IF NOT EXISTS books_meta (
    source          TEXT NOT NULL,
    book_id         TEXT NOT NULL,
    authors         TEXT NOT NULL DEFAULT '[]',
    view_count      INTEGER,
    last_viewed_at  REAL,
    hidden          INTEGER,
    genre           TEXT,
    read_state      TEXT,
    series_id       TEXT,
    series_title    TEXT,
    series_index    REAL,
    volume          INTEGER,
    publisher       TEXT,
    asin            TEXT,
    isbn            TEXT,
    release_date    TEXT,
    PRIMARY KEY (source, book_id)
);

CREATE TABLE IF NOT EXISTS genres (
    source      TEXT NOT NULL,
    genre       TEXT NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (source, genre)
);

CREATE TABLE IF NOT EXISTS ui_filters (
    source              TEXT NOT NULL,
    read_state_filter   TEXT NOT NULL DEFAULT '',
    genre_filter        TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (source)
);

CREATE TABLE IF NOT EXISTS group_pins (
    source    TEXT NOT NULL,
    pin_type  TEXT NOT NULL,
    group_id  TEXT NOT NULL,
    book_name TEXT NOT NULL,
    PRIMARY KEY (source, pin_type, group_id)
);
"""


def _db_path() -> str:
    return os.path.join(config.META_DB_DIR, "meta2.db")


def connect() -> sqlite3.Connection:
    """meta2.db へ接続して返す。呼び出し側が close する低レベルAPI。"""
    os.makedirs(config.META_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(_db_path(), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    """commit/rollback と close を必ず行う短命接続context manager。"""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(_CREATE_DDL)


def init_db() -> None:
    """テーブル作成を実行する。

    アプリ起動時（lifespan）に 1 回だけ呼ぶ。
    """
    with db_connection() as conn:
        create_tables(conn)


# ---------------------------------------------------------------------------
# Row ↔ MetaEntry 変換ヘルパー
# ---------------------------------------------------------------------------


def row_to_entry(row: sqlite3.Row) -> dict:
    """SQLite の Row を MetaEntry 相当の dict に変換する。

    NotRequired フィールドは NULL の場合に省略する（保存前と同一構造を再現）。
    """
    entry: dict = {"authors": json.loads(row["authors"])}
    if row["view_count"] is not None:
        entry["view_count"] = row["view_count"]
    if row["last_viewed_at"] is not None:
        entry["last_viewed_at"] = row["last_viewed_at"]
    if row["hidden"]:
        entry["hidden"] = True
    for key in ("genre", "read_state", "series_id", "series_title", "publisher", "asin", "isbn", "release_date"):
        val = row[key]
        if val is not None:
            entry[key] = val
    if row["series_index"] is not None:
        entry["series_index"] = row["series_index"]
    if row["volume"] is not None:
        entry["volume"] = row["volume"]
    return entry


def entry_to_params(source: str, book_id: str, entry: dict) -> tuple:
    """MetaEntry → INSERT/REPLACE パラメータタプルに変換する。"""
    return (
        source,
        book_id,
        json.dumps(entry.get("authors", []), ensure_ascii=False),
        entry.get("view_count"),
        entry.get("last_viewed_at"),
        1 if entry.get("hidden") else None,
        entry.get("genre"),
        entry.get("read_state"),
        entry.get("series_id"),
        entry.get("series_title"),
        entry.get("series_index"),
        entry.get("volume"),
        entry.get("publisher"),
        entry.get("asin"),
        entry.get("isbn"),
        entry.get("release_date"),
    )


_UPSERT_SQL = """
INSERT OR REPLACE INTO books_meta
    (source, book_id, authors, view_count, last_viewed_at, hidden, genre,
     read_state, series_id, series_title, series_index, volume,
     publisher, asin, isbn, release_date)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""


def upsert_entry(conn: sqlite3.Connection, source: str, book_id: str, entry: dict[str, object]) -> None:
    conn.execute(_UPSERT_SQL, entry_to_params(source, book_id, entry))
