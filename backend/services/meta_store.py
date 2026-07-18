"""meta2.db（SQLite）の読み書き・ロック管理。

詳細仕様: docs/design/詳細設計/詳細設計書_バックエンド編.md「閲覧回数 / 最近見た順ソート（バックエンド側）」節
"""

import sqlite3
import threading
from collections.abc import Callable
from copy import deepcopy
from typing import Literal, NotRequired, TypedDict

from services.meta_db import create_tables, db_connection, row_to_entry, upsert_entry
from utils.locks import SourceLockManager

ReadState = Literal["unread", "reading", "done"]
VALID_READ_STATES: tuple[ReadState, ...] = ("unread", "reading", "done")


class MetaEntry(TypedDict):
    authors: list[str]
    view_count: NotRequired[int]
    last_viewed_at: NotRequired[float]
    hidden: NotRequired[bool]
    genre: NotRequired[str]
    read_state: NotRequired[ReadState]
    series_id: NotRequired[str]
    series_title: NotRequired[str]
    series_index: NotRequired[float]
    volume: NotRequired[int | None]
    publisher: NotRequired[str]
    asin: NotRequired[str]
    isbn: NotRequired[str]
    release_date: NotRequired[str]


MetaDict = dict[str, MetaEntry]

_lock_manager = SourceLockManager()


def get_lock(source: str) -> threading.Lock:
    return _lock_manager.get(source)


def make_key(path: str, name: str) -> str:
    return f"{path}/{name}" if path else name


def _ensure(conn: sqlite3.Connection) -> None:
    """テーブルが存在しない場合（テスト等）に自動作成する。"""
    create_tables(conn)


def _load_meta_from_conn(conn: sqlite3.Connection, source: str) -> MetaDict:
    rows = conn.execute("SELECT * FROM books_meta WHERE source=?", (source,)).fetchall()
    return {row["book_id"]: row_to_entry(row) for row in rows}  # type: ignore[return-value]


def load_meta(source: str) -> MetaDict:
    with db_connection() as conn:
        _ensure(conn)
        return _load_meta_from_conn(conn, source)


def save_meta(source: str, data: MetaDict) -> None:
    with db_connection() as conn:
        _ensure(conn)
        existing = {row[0] for row in conn.execute("SELECT book_id FROM books_meta WHERE source=?", (source,))}
        to_delete = existing - data.keys()
        if to_delete:
            conn.executemany(
                "DELETE FROM books_meta WHERE source=? AND book_id=?",
                [(source, bid) for bid in to_delete],
            )
        for book_id, entry in data.items():
            upsert_entry(conn, source, book_id, entry)  # type: ignore[arg-type]


def update_meta_locked(source: str, updater: Callable[[MetaDict], None]) -> None:
    """同一transactionでupdaterを適用し、変更された行だけ保存する。"""
    with get_lock(source):
        with db_connection() as conn:
            _ensure(conn)
            meta = _load_meta_from_conn(conn, source)
            original = deepcopy(meta)
            updater(meta)

            deleted = original.keys() - meta.keys()
            if deleted:
                conn.executemany(
                    "DELETE FROM books_meta WHERE source=? AND book_id=?",
                    [(source, book_id) for book_id in deleted],
                )
            for book_id, entry in meta.items():
                if original.get(book_id) != entry:
                    upsert_entry(conn, source, book_id, entry)  # type: ignore[arg-type]


def merge_entry_fields(
    entry: dict,
    *,
    authors: list[str] | None = None,
    hidden: bool | None = None,
    genre: str | None = None,
    read_state: str | None = None,
) -> dict:
    """部分的に指定されたフィールドだけを上書きしたエントリを返す（非破壊）。

    - `authors`: list（空可）。`None` 指定なら変更しない。
    - `hidden`: True なら設定 / False なら削除。`None` 指定なら変更しない。
    - `genre`: 空文字なら削除、文字列なら設定。`None` 指定なら変更しない。
    - `read_state`: 空文字なら削除、`'unread' | 'reading' | 'done'` なら設定。`None` 指定なら変更しない。
      不正値はバリデーションエラーとして ValueError。
    """
    merged = dict(entry)
    if authors is not None:
        merged["authors"] = authors
    if hidden is True:
        merged["hidden"] = True
    elif hidden is False:
        merged.pop("hidden", None)
    if genre is not None:
        if genre:
            merged["genre"] = genre
        else:
            merged.pop("genre", None)
    if read_state is not None:
        if read_state == "":
            merged.pop("read_state", None)
        elif read_state in VALID_READ_STATES:
            merged["read_state"] = read_state
        else:
            raise ValueError(f"Invalid read_state: {read_state!r}")
    return merged


def has_meaningful_value(entry: dict) -> bool:
    """エントリに「空 list 以外」の意味のある値があるかを返す。"""
    return any(not (isinstance(v, list) and not v) for v in entry.values())
