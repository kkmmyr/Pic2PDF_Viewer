"""hitomi.la で検出した作品の SQLite 永続化と旧JSON移行。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Literal, TypedDict, cast

from services import meta_db

ArrivalStatus = Literal["unread", "read", "all"]


class ArrivalItem(TypedDict, total=False):
    id: int
    artist: str
    display_artist: str
    title: str
    language: str
    type: str
    page_count: int
    published_at: str | None
    discovered_at: str
    url: str
    is_read: bool
    read_at: str | None
    dismissed: bool


class ArrivalPage(TypedDict):
    items: list[ArrivalItem]
    total: int
    unread_count: int
    read_count: int


_INSERT_SQL = """
INSERT INTO hitomi_arrivals (
    gallery_id, artist, display_artist, title, language, gallery_type,
    page_count, published_at, discovered_at, url, is_read, read_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(gallery_id) DO NOTHING
"""


def _legacy_path(data_dir: Path) -> Path:
    return data_dir / "new_arrivals.json"


def _item_params(item: ArrivalItem, *, legacy: bool) -> tuple[object, ...] | None:
    gallery_id = item.get("id")
    if gallery_id is None:
        return None
    is_read = bool(item.get("dismissed")) if legacy else bool(item.get("is_read"))
    return (
        gallery_id,
        item.get("artist", ""),
        item.get("display_artist", ""),
        item.get("title", ""),
        item.get("language", ""),
        item.get("type", ""),
        item.get("page_count", 0),
        item.get("published_at"),
        item.get("discovered_at", ""),
        item.get("url", ""),
        1 if is_read else 0,
        item.get("read_at"),
    )


def import_legacy_json(data_dir: Path) -> int:
    """旧 new_arrivals.json を冪等に取り込む。JSON自体は削除しない。"""
    meta_db.init_db()
    path = _legacy_path(data_dir)
    if not path.is_file():
        return 0
    stat = path.stat()
    source_path = str(path.resolve())
    with meta_db.db_connection() as conn:
        imported = conn.execute(
            """
            SELECT source_mtime_ns, source_size
            FROM hitomi_legacy_imports
            WHERE source_path = ?
            """,
            (source_path,),
        ).fetchone()
    if imported and imported["source_mtime_ns"] == stat.st_mtime_ns and imported["source_size"] == stat.st_size:
        return 0

    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    items = payload.get("items", [])
    if not isinstance(items, list):
        raise ValueError("new_arrivals.json items must be a list")

    added = 0
    with meta_db.db_connection() as conn:
        for raw_item in items:
            if not isinstance(raw_item, dict):
                continue
            params = _item_params(cast(ArrivalItem, raw_item), legacy=True)
            if params is None:
                continue
            added += conn.execute(_INSERT_SQL, params).rowcount
        conn.execute(
            """
            INSERT INTO hitomi_legacy_imports (
                source_path, source_mtime_ns, source_size, imported_at
            ) VALUES (?, ?, ?, datetime('now', '+9 hours'))
            ON CONFLICT(source_path) DO UPDATE SET
                source_mtime_ns = excluded.source_mtime_ns,
                source_size = excluded.source_size,
                imported_at = excluded.imported_at
            """,
            (source_path, stat.st_mtime_ns, stat.st_size),
        )
    return added


def merge_new_items(items: list[ArrivalItem]) -> int:
    """検出作品を追加し、既存gallery_idは変更せず無視する。"""
    if not items:
        return 0
    meta_db.init_db()
    added = 0
    with meta_db.db_connection() as conn:
        for item in items:
            params = _item_params(item, legacy=False)
            if params is None:
                continue
            added += conn.execute(_INSERT_SQL, params).rowcount
    return added


def _row_to_item(row: sqlite3.Row) -> ArrivalItem:
    return {
        "id": row["gallery_id"],
        "artist": row["artist"],
        "display_artist": row["display_artist"],
        "title": row["title"],
        "language": row["language"],
        "type": row["gallery_type"],
        "page_count": row["page_count"],
        "published_at": row["published_at"],
        "discovered_at": row["discovered_at"],
        "url": row["url"],
        "is_read": bool(row["is_read"]),
        "read_at": row["read_at"],
    }


def list_arrivals(status: ArrivalStatus, offset: int, limit: int) -> ArrivalPage:
    """指定既読状態の作品を検出日時降順で返す。"""
    meta_db.init_db()
    where = ""
    if status == "unread":
        where = "WHERE is_read = 0"
    elif status == "read":
        where = "WHERE is_read = 1"

    with meta_db.db_connection() as conn:
        unread_count = conn.execute("SELECT COUNT(*) FROM hitomi_arrivals WHERE is_read = 0").fetchone()[0]
        read_count = conn.execute("SELECT COUNT(*) FROM hitomi_arrivals WHERE is_read = 1").fetchone()[0]
        total = conn.execute(f"SELECT COUNT(*) FROM hitomi_arrivals {where}").fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT * FROM hitomi_arrivals
            {where}
            ORDER BY discovered_at DESC, gallery_id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

    return {
        "items": [_row_to_item(row) for row in rows],
        "total": total,
        "unread_count": unread_count,
        "read_count": read_count,
    }


def dismiss(gallery_id: int) -> bool:
    """未読作品を既読化し、新規操作分の既読日時をJSTで記録する。"""
    meta_db.init_db()
    with meta_db.db_connection() as conn:
        updated = conn.execute(
            """
            UPDATE hitomi_arrivals
            SET is_read = 1, read_at = datetime('now', '+9 hours')
            WHERE gallery_id = ? AND is_read = 0
            """,
            (gallery_id,),
        ).rowcount
    return updated > 0


def dismiss_all() -> int:
    """全未読作品を同一既読日時で既読化する。"""
    meta_db.init_db()
    with meta_db.db_connection() as conn:
        return conn.execute(
            """
            UPDATE hitomi_arrivals
            SET is_read = 1, read_at = datetime('now', '+9 hours')
            WHERE is_read = 0
            """
        ).rowcount
