import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import lancedb

from tools.server_backup import create_backup, verify_latest_backup


def _create_sqlite(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample VALUES (?)", (value,))
        connection.commit()
    finally:
        connection.close()


def _create_lance(path: Path) -> None:
    database = lancedb.connect(path)
    database.create_table("chunks", data=[{"id": 1, "text": "sample"}])


def test_create_backup_captures_wal_and_all_databases(tmp_path: Path) -> None:
    meta_db = tmp_path / "source" / "meta2.db"
    novel_db = tmp_path / "source" / "novel.db"
    kindle_catalog_db = tmp_path / "source" / "kindle_catalog.db"
    lance_db = tmp_path / "source" / "novel.lancedb"
    meta_db.parent.mkdir(parents=True)
    writer = sqlite3.connect(meta_db)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE sample (value TEXT NOT NULL)")
    writer.execute("INSERT INTO sample VALUES ('committed-in-wal')")
    writer.commit()
    _create_sqlite(novel_db, "novel")
    _create_sqlite(kindle_catalog_db, "kindle")
    _create_lance(lance_db)

    try:
        snapshot = create_backup(
            meta_db=meta_db,
            novel_db=novel_db,
            lance_db=lance_db,
            backup_dir=tmp_path / "backups",
            label="2026-07-18_020000",
            retention_days=14,
            kindle_catalog_db=kindle_catalog_db,
        )
    finally:
        writer.close()

    with sqlite3.connect(snapshot / "meta2.db") as connection:
        assert connection.execute("SELECT value FROM sample").fetchone() == ("committed-in-wal",)
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"]["meta2"]["integrity_check"] == "ok"
    assert manifest["artifacts"]["novel"]["integrity_check"] == "ok"
    assert manifest["artifacts"]["kindle_catalog"]["integrity_check"] == "ok"
    assert manifest["artifacts"]["lance"]["tables"] == {"chunks": 1}


def test_create_backup_records_missing_optional_databases(tmp_path: Path) -> None:
    meta_db = tmp_path / "meta2.db"
    _create_sqlite(meta_db, "meta")

    snapshot = create_backup(
        meta_db=meta_db,
        novel_db=tmp_path / "missing-novel.db",
        lance_db=tmp_path / "missing.lancedb",
        backup_dir=tmp_path / "backups",
        label="only-meta",
        retention_days=14,
    )

    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"]["novel"]["status"] == "not_present"
    assert manifest["artifacts"]["lance"]["status"] == "not_present"


def test_retention_and_separate_restore_verification(tmp_path: Path) -> None:
    meta_db = tmp_path / "meta2.db"
    _create_sqlite(meta_db, "meta")
    backup_dir = tmp_path / "backups"
    current_time = datetime(2026, 7, 18, tzinfo=UTC)
    old_snapshot = create_backup(
        meta_db=meta_db,
        novel_db=tmp_path / "missing-novel.db",
        lance_db=tmp_path / "missing.lancedb",
        backup_dir=backup_dir,
        label="old",
        retention_days=14,
        now=current_time - timedelta(days=15),
    )

    create_backup(
        meta_db=meta_db,
        novel_db=tmp_path / "missing-novel.db",
        lance_db=tmp_path / "missing.lancedb",
        backup_dir=backup_dir,
        label="latest",
        retention_days=14,
        now=current_time,
    )

    assert not old_snapshot.exists()
    restore_dir = tmp_path / "restore-tests"
    result = verify_latest_backup(backup_dir=backup_dir, restore_test_dir=restore_dir)
    assert result["snapshot"] == "latest"
    assert result["checks"] == {"meta2": "ok"}
    marker = json.loads((restore_dir / "last-success.json").read_text(encoding="utf-8"))
    assert marker["snapshot"] == "latest"
    assert not any(path.is_dir() for path in restore_dir.iterdir())
