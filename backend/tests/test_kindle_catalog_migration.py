"""Kindle 購入カタログのレガシー移行テスト。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import config
from services.kindle_catalog.connection import with_db
from services.kindle_catalog.legacy_migration import commit, preview
from services.kindle_catalog.migrations import upgrade_head
from services.kindle_catalog.repository import list_books, stats


def _create_legacy_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE books (
            asin TEXT PRIMARY KEY, title TEXT NOT NULL, title_normalized TEXT,
            authors TEXT, publisher TEXT, isbn TEXT, isbn13 TEXT, category TEXT,
            book_type TEXT, genre TEXT, kindle_acquisition_date TEXT,
            total_reading_ms INTEGER, last_read_at TEXT, is_completed INTEGER,
            created_at TEXT, updated_at TEXT, cover_local_path TEXT
        );
        CREATE TABLE purchases (
            id INTEGER PRIMARY KEY, order_number TEXT, order_date TEXT, asin TEXT,
            title TEXT, price INTEGER, order_status TEXT, digital_order_item_id TEXT,
            created_at TEXT
        );
        CREATE TABLE borrowings (
            id INTEGER PRIMARY KEY, asin TEXT, title TEXT, authors TEXT,
            loan_program TEXT, loan_status TEXT, loan_creation_date TEXT,
            loan_acceptance_date TEXT, end_date TEXT, created_at TEXT
        );
        CREATE TABLE returns (
            id INTEGER PRIMARY KEY, asin TEXT, title TEXT, order_id TEXT,
            refund_amount INTEGER, return_date TEXT, return_status TEXT, created_at TEXT
        );
        CREATE TABLE series (
            id INTEGER PRIMARY KEY, name TEXT, author TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE book_series (
            asin TEXT PRIMARY KEY, series_id INTEGER, volume_number REAL,
            volume_label TEXT, detection_method TEXT, is_manually_edited INTEGER,
            confidence REAL, updated_at TEXT
        );
        CREATE TABLE series_subscriptions (
            series_asin TEXT PRIMARY KEY, subscription_id TEXT, title TEXT,
            series_id INTEGER, resolution_method TEXT, imported_at TEXT
        );
        CREATE TABLE book_reviews (id INTEGER PRIMARY KEY, review_text TEXT);

        INSERT INTO books VALUES (
            'B000TEST01', 'テスト作品 1巻', NULL, '著者A,著者B', '出版社',
            NULL, NULL, 'unknown', 'comic', 'マンガ,女性マンガ',
            '2026-01-02 03:04:05', 1234, NULL, 1,
            '2026-01-02 03:04:05', '2026-01-02 03:04:05',
            'covers/garbage.jpg'
        );
        INSERT INTO purchases VALUES (
            1, 'ORDER-1', '2026-01-02', 'B000TEST01', 'テスト作品 1巻',
            500, 'SUCCESS', 'ITEM-1', '2026-01-02 03:04:05'
        );
        INSERT INTO series VALUES (7, 'テスト作品', '著者A', NULL, NULL);
        INSERT INTO book_series VALUES (
            'B000TEST01', 7, 1.0, '1', 'legacy', 1, 1.0, NULL
        );
        INSERT INTO series_subscriptions VALUES (
            'SERIES-ASIN', 'SUB-1', 'テスト作品', 7, 'title_match', NULL
        );
        INSERT INTO book_reviews VALUES (1, '移行してはいけない感想');
        """
    )
    conn.commit()
    conn.close()


def test_preview_and_commit_migrate_catalog_without_legacy_images(tmp_path, monkeypatch):
    legacy_path = tmp_path / "legacy.db"
    target_dir = tmp_path / "target"
    _create_legacy_db(legacy_path)
    monkeypatch.setattr(config, "META_DB_DIR", str(target_dir))
    monkeypatch.setattr(config, "KINDLE_LEGACY_DB_PATH", str(legacy_path))
    upgrade_head()

    result = preview()

    assert result["counts"]["books"] == 1
    assert result["excluded_counts"]["book_reviews"] == 1
    assert result["images_migrated"] is False

    committed = commit(result["confirmation_token"])

    assert committed["status"] == "succeeded"
    assert committed["images_migrated"] is False
    assert stats()["books"] == 1
    catalog = list_books(q=None, book_type=None, ownership=None, capture_state=None, page=1, page_size=50)
    assert catalog["items"][0]["authors"] == ["著者A", "著者B"]
    assert catalog["items"][0]["genres"] == ["マンガ", "女性マンガ"]
    assert catalog["items"][0]["ownership"] == "purchased"
    with with_db() as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        book_columns = {row[1] for row in conn.execute("PRAGMA table_info(books)")}
    assert "book_reviews" not in tables
    assert "cover_local_path" not in book_columns


def test_commit_rejects_unknown_confirmation_token(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "META_DB_DIR", str(tmp_path / "target"))
    upgrade_head()

    try:
        commit("unknown-token")
    except ValueError as exc:
        assert "確認トークン" in str(exc)
    else:
        raise AssertionError("invalid token must be rejected")
