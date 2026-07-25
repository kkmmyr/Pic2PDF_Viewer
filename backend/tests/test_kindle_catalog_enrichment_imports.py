"""Kindle Info とシリーズ自動購入の差分取り込みテスト。"""

import json
from pathlib import Path

import config
from services.kindle_catalog.connection import with_db
from services.kindle_catalog.enrichment_imports import (
    run_autobuy_import,
    run_kindle_info_import,
)
from services.kindle_catalog.migrations import upgrade_head


def _write_csv(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8-sig")


def _prepare(tmp_path: Path, monkeypatch) -> Path:
    source = tmp_path / "amazon"
    source.mkdir()
    monkeypatch.setattr(config, "META_DB_DIR", str(tmp_path / "target"))
    monkeypatch.setattr(config, "AMAZON_DATA_DIR", str(source))
    upgrade_head()
    with with_db() as conn:
        conn.execute(
            """
            INSERT INTO books(asin,title,title_normalized,category,book_type)
            VALUES ('B000KNOWN','作品 第1巻','作品','kindle','unknown')
            """
        )
        series_id = conn.execute("INSERT INTO series(name,author_key) VALUES ('作品','')").lastrowid
        conn.execute(
            """
            INSERT INTO book_series(asin,series_id,is_manually_edited)
            VALUES ('B000KNOWN',?,0)
            """,
            (series_id,),
        )
    return source


def test_kindle_info_updates_existing_books_only_and_is_idempotent(tmp_path, monkeypatch):
    source = _prepare(tmp_path, monkeypatch)
    _write_csv(
        source / "Kindle.UnifiedLibraryIndex.CustomerGenres_FE.csv",
        ["ASIN,Genre", "B000KNOWN,コミック", "B000UNKNOWN,コミック"],
    )
    _write_csv(
        source / "Kindle.UnifiedLibraryIndex.CustomerAuthorNameRelationship_FE.csv",
        ["ASIN,Author Name", "B000KNOWN,著者A"],
    )
    _write_csv(
        source / "Kindle.SagaSeriesInfra.CollectionRightsDatastore.csv",
        [
            "record-type,item-ASIN,item-position-in-series,series-ASIN",
            "Item,B000KNOWN,1,B000SERIES",
        ],
    )
    _write_csv(
        source / "Kindle.Devices.autoMarkAsRead.csv",
        ["file_auto_marked_as_read", "B000KNOWN"],
    )

    first = run_kindle_info_import()
    second = run_kindle_info_import()

    assert first["files_processed"] == 4
    assert first["records_processed"] == 4
    assert first["records_skipped"] == 1
    assert second["files_processed"] == 0
    assert second["files_skipped"] == 4
    with with_db() as conn:
        book = conn.execute("SELECT book_type,is_completed FROM books WHERE asin='B000KNOWN'").fetchone()
        assert dict(book) == {"book_type": "comic", "is_completed": 1}
        assert conn.execute("SELECT COUNT(*) FROM books WHERE asin='B000UNKNOWN'").fetchone()[0] == 0
        assert (
            conn.execute(
                """
            SELECT a.name FROM authors a
            JOIN book_authors ba ON ba.author_id=a.id
            WHERE ba.asin='B000KNOWN'
            """
            ).fetchone()[0]
            == "著者A"
        )
        assert conn.execute("SELECT volume_number FROM book_series WHERE asin='B000KNOWN'").fetchone()[0] == 1.0


def test_autobuy_replaces_subscriptions_and_skips_unchanged_file(tmp_path, monkeypatch):
    source = _prepare(tmp_path, monkeypatch)
    _write_csv(
        source / "Kindle.SagaSeriesInfra.CollectionRightsDatastore.csv",
        [
            "record-type,item-ASIN,item-position-in-series,series-ASIN",
            "Item,B000KNOWN,1,B000SERIES",
        ],
    )
    payload_path = source / "kindle-series-autobuy.json"
    payload_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "subscription_id": "SUB-1",
                        "series_asin": "B000SERIES",
                        "title": "作品",
                    },
                    {
                        "subscription_id": "PRIME",
                        "series_asin": "PRIME",
                        "title": "Amazon Prime",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    first = run_autobuy_import()
    second = run_autobuy_import()

    assert first["records_processed"] == 1
    assert first["records_skipped"] == 1
    assert first["unresolved"] == 0
    assert second["files_skipped"] == 1
    with with_db() as conn:
        row = conn.execute("SELECT title,resolution_method FROM series_subscriptions").fetchone()
        assert dict(row) == {"title": "作品", "resolution_method": "collection_rights"}
