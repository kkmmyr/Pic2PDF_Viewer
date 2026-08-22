"""旧 `kindle購入履歴` SQLite DB からの画像非依存移行。"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import config
from services._title_normalizer import normalize_title
from services.kindle_catalog.connection import with_db
from utils.dt import jst_now

_SUPPORTED_TABLES = (
    "books",
    "purchases",
    "borrowings",
    "returns",
    "series",
    "book_series",
    "series_subscriptions",
)
_EXCLUDED_TABLES = (
    "book_reviews",
    "enrichment_candidates",
    "series_extraction_log",
    "reading_day_stats",
)
_REQUIRED_BOOK_COLUMNS = {"asin", "title"}


@dataclass(frozen=True)
class _PreviewGrant:
    fingerprint: str
    expires_at: datetime


_preview_grants: dict[str, _PreviewGrant] = {}


def _legacy_path() -> Path:
    raw = config.KINDLE_LEGACY_DB_PATH
    if not raw:
        raise ValueError("KINDLE_LEGACY_DB_PATH が設定されていません")
    path = Path(raw)
    if not path.is_file():
        raise ValueError("設定されたレガシー DB が見つかりません")
    return path


def _fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _open_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _counts(conn: sqlite3.Connection, tables: tuple[str, ...]) -> dict[str, int]:
    existing = _table_names(conn)
    return {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] if table in existing else 0
        for table in tables
    }


def preview() -> dict:
    """移行元の整合性と件数を検査し、commit 用の短期トークンを返す。"""
    path = _legacy_path()
    fingerprint = _fingerprint(path)
    with _open_readonly(path) as legacy:
        integrity = legacy.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"レガシー DB の整合性検査に失敗しました: {integrity}")
        tables = _table_names(legacy)
        if "books" not in tables or not _REQUIRED_BOOK_COLUMNS.issubset(_table_columns(legacy, "books")):
            raise ValueError("対応していないレガシー DB スキーマです")
        counts = _counts(legacy, _SUPPORTED_TABLES)
        excluded_counts = _counts(legacy, _EXCLUDED_TABLES)
        missing_asin = legacy.execute("SELECT COUNT(*) FROM books WHERE asin IS NULL OR TRIM(asin) = ''").fetchone()[0]

    now = jst_now()
    expires_at = now + timedelta(minutes=15)
    token = secrets.token_urlsafe(32)
    _preview_grants[token] = _PreviewGrant(fingerprint=fingerprint, expires_at=expires_at)
    return {
        "configured": True,
        "source_name": path.name,
        "source_size": path.stat().st_size,
        "fingerprint": fingerprint,
        "integrity": "ok",
        "counts": counts,
        "excluded_counts": excluded_counts,
        "missing_asin": missing_asin,
        "confirmation_token": token,
        "expires_at": expires_at.isoformat(),
        "images_migrated": False,
    }


def _text(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _name_key(name: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", name).casefold().split())


def _split_values(value: object | None) -> list[str]:
    if value is None:
        return []
    normalized = str(value).replace("、", ",").replace(";", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def _migrate_books(legacy: sqlite3.Connection, target: sqlite3.Connection) -> tuple[int, int]:
    processed = 0
    skipped = 0
    for row in legacy.execute("SELECT * FROM books"):
        asin = _text(row["asin"])
        title = _text(row["title"])
        if not asin or not title:
            skipped += 1
            continue
        target.execute(
            """
            INSERT INTO books (
                asin, title, title_normalized, publisher, isbn, isbn13, category,
                book_type, kindle_acquisition_date, total_reading_ms, last_read_at,
                is_completed, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(asin) DO UPDATE SET
                title=excluded.title,
                title_normalized=excluded.title_normalized,
                publisher=COALESCE(excluded.publisher, books.publisher),
                isbn=COALESCE(excluded.isbn, books.isbn),
                isbn13=COALESCE(excluded.isbn13, books.isbn13),
                category=excluded.category,
                book_type=excluded.book_type,
                kindle_acquisition_date=COALESCE(excluded.kindle_acquisition_date, books.kindle_acquisition_date),
                total_reading_ms=COALESCE(excluded.total_reading_ms, books.total_reading_ms),
                last_read_at=COALESCE(excluded.last_read_at, books.last_read_at),
                is_completed=COALESCE(excluded.is_completed, books.is_completed),
                updated_at=excluded.updated_at
            """,
            (
                asin,
                title,
                _text(row["title_normalized"]) or normalize_title(title),
                _text(row["publisher"]),
                _text(row["isbn"]),
                _text(row["isbn13"]),
                _text(row["category"]) or "unknown",
                _text(row["book_type"]) or "unknown",
                _text(row["kindle_acquisition_date"]),
                row["total_reading_ms"],
                _text(row["last_read_at"]),
                row["is_completed"],
                _text(row["created_at"]),
                _text(row["updated_at"]),
            ),
        )
        for order, author in enumerate(_split_values(row["authors"])):
            key = _name_key(author)
            target.execute(
                "INSERT INTO authors(name, name_key) VALUES (?, ?) "
                "ON CONFLICT(name_key) DO UPDATE SET name=excluded.name",
                (author, key),
            )
            author_id = target.execute("SELECT id FROM authors WHERE name_key=?", (key,)).fetchone()[0]
            target.execute(
                "INSERT INTO book_authors(asin, author_id, sort_order) VALUES (?, ?, ?) "
                "ON CONFLICT(asin, author_id) DO UPDATE SET sort_order=excluded.sort_order",
                (asin, author_id, order),
            )
        for genre in _split_values(row["genre"]):
            target.execute(
                "INSERT INTO book_genres(asin, genre) VALUES (?, ?) ON CONFLICT(asin, genre) DO NOTHING",
                (asin, genre),
            )
        processed += 1
    return processed, skipped


def _copy_history(legacy: sqlite3.Connection, target: sqlite3.Connection, table: str) -> int:
    columns_by_table = {
        "purchases": (
            "order_number",
            "order_date",
            "asin",
            "title",
            "price",
            "order_status",
            "digital_order_item_id",
            "created_at",
        ),
        "borrowings": (
            "asin",
            "title",
            "authors",
            "loan_program",
            "loan_status",
            "loan_creation_date",
            "loan_acceptance_date",
            "end_date",
            "created_at",
        ),
        "returns": (
            "asin",
            "title",
            "order_id",
            "refund_amount",
            "return_date",
            "return_status",
            "created_at",
        ),
    }
    conflict_by_table = {
        "purchases": "(order_number, asin, title)",
        "borrowings": "(asin, loan_creation_date)",
        "returns": "(asin, order_id, return_date)",
    }
    columns = columns_by_table[table]
    placeholders = ", ".join("?" for _ in columns)
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT {conflict_by_table[table]} DO NOTHING"
    )
    rows = [tuple(row[column] for column in columns) for row in legacy.execute(f"SELECT * FROM {table}")]
    target.executemany(sql, rows)
    return len(rows)


def _migrate_series(legacy: sqlite3.Connection, target: sqlite3.Connection) -> int:
    rows = legacy.execute("SELECT * FROM series").fetchall()
    for row in rows:
        author = _text(row["author"])
        target.execute(
            """
            INSERT INTO series(id, name, author, author_key, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, author=excluded.author,
                author_key=excluded.author_key, updated_at=excluded.updated_at
            """,
            (
                row["id"],
                row["name"],
                author,
                _name_key(author or ""),
                _text(row["created_at"]),
                _text(row["updated_at"]),
            ),
        )
    return len(rows)


def _migrate_book_series(legacy: sqlite3.Connection, target: sqlite3.Connection) -> int:
    columns = (
        "asin",
        "series_id",
        "volume_number",
        "volume_label",
        "detection_method",
        "is_manually_edited",
        "confidence",
        "updated_at",
    )
    rows = legacy.execute("SELECT * FROM book_series").fetchall()
    for row in rows:
        target.execute(
            f"""
            INSERT INTO book_series({", ".join(columns)})
            VALUES ({", ".join("?" for _ in columns)})
            ON CONFLICT(asin) DO UPDATE SET
                series_id=excluded.series_id,
                volume_number=excluded.volume_number,
                volume_label=excluded.volume_label,
                detection_method=excluded.detection_method,
                is_manually_edited=excluded.is_manually_edited,
                confidence=excluded.confidence,
                updated_at=excluded.updated_at
            """,
            tuple(row[column] for column in columns),
        )
    return len(rows)


def _migrate_subscriptions(legacy: sqlite3.Connection, target: sqlite3.Connection) -> int:
    columns = (
        "series_asin",
        "subscription_id",
        "title",
        "series_id",
        "resolution_method",
        "imported_at",
    )
    rows = legacy.execute("SELECT * FROM series_subscriptions").fetchall()
    for row in rows:
        target.execute(
            f"""
            INSERT INTO series_subscriptions({", ".join(columns)})
            VALUES ({", ".join("?" for _ in columns)})
            ON CONFLICT(series_asin) DO UPDATE SET
                subscription_id=excluded.subscription_id,
                title=excluded.title,
                series_id=excluded.series_id,
                resolution_method=excluded.resolution_method,
                imported_at=excluded.imported_at
            """,
            tuple(row[column] for column in columns),
        )
    return len(rows)


def commit(confirmation_token: str) -> dict:
    """preview 済み fingerprint と一致する DB からカタログ情報だけを移行する。"""
    grant = _preview_grants.pop(confirmation_token, None)
    if grant is None:
        raise ValueError("確認トークンが無効です。もう一度プレビューしてください")
    if jst_now() > grant.expires_at:
        raise ValueError("確認トークンの有効期限が切れました")
    path = _legacy_path()
    if _fingerprint(path) != grant.fingerprint:
        raise ValueError("プレビュー後にレガシー DB が変更されました")

    now = jst_now().isoformat()
    with _open_readonly(path) as legacy, with_db() as target:
        run_id = target.execute(
            """
            INSERT INTO import_runs(
                source_kind, status, started_at,
                files_processed, records_processed, records_skipped
            ) VALUES ('legacy_db', 'running', ?, 0, 0, 0)
            """,
            (now,),
        ).lastrowid
        books_count, skipped = _migrate_books(legacy, target)
        processed = books_count
        existing = _table_names(legacy)
        for table in ("purchases", "borrowings", "returns"):
            if table in existing:
                processed += _copy_history(legacy, target, table)
        if "series" in existing:
            processed += _migrate_series(legacy, target)
        if "book_series" in existing:
            processed += _migrate_book_series(legacy, target)
        if "series_subscriptions" in existing:
            processed += _migrate_subscriptions(legacy, target)
        target.execute(
            """
            UPDATE import_runs
            SET status='succeeded', finished_at=?, files_processed=1,
                records_processed=?, records_skipped=?
            WHERE id=?
            """,
            (jst_now().isoformat(), processed, skipped, run_id),
        )
        integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"移行後 DB の整合性検査に失敗しました: {integrity}")

    return {
        "run_id": run_id,
        "status": "succeeded",
        "records_processed": processed,
        "records_skipped": skipped,
        "images_migrated": False,
    }


def source_status() -> dict:
    """既存import互換。通常経路はlegacy_source_statusを直接参照する。"""
    from services.kindle_catalog.legacy_source_status import (
        source_status as current_source_status,
    )

    return current_source_status()
