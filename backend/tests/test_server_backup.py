import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import lancedb
import pytest

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


def _dense_row(chunk_id: int, *, text: str | None = None, embedding_size: int = 1024) -> dict:
    page_no = chunk_id - 100
    return {
        "chunk_id": chunk_id,
        "book_name": "sample-book",
        "page_no": page_no,
        "text": text or f"sample-{page_no}",
        "char_count": 8,
        "page_count": 2,
        "embedding": [0.1] * embedding_size,
    }


def _create_novel_sqlite(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE books (id INTEGER PRIMARY KEY, name TEXT NOT NULL, page_count INTEGER NOT NULL);
            CREATE TABLE pages (
                id INTEGER PRIMARY KEY,
                book_id INTEGER NOT NULL,
                page_no INTEGER NOT NULL,
                char_count INTEGER NOT NULL
            );
            CREATE TABLE chunks (
                id INTEGER PRIMARY KEY,
                page_id INTEGER NOT NULL,
                text TEXT NOT NULL
            );
            INSERT INTO books VALUES (1, 'sample-book', 2);
            INSERT INTO pages VALUES (11, 1, 1, 8), (12, 1, 2, 8);
            INSERT INTO chunks VALUES (101, 11, 'sample-1'), (102, 12, 'sample-2');
            """
        )
        connection.commit()
    finally:
        connection.close()


def _create_lance(path: Path, rows: list[dict] | None = None) -> None:
    database = lancedb.connect(path)
    database.create_table("chunks", data=rows or [_dense_row(101), _dense_row(102)])


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
    _create_novel_sqlite(novel_db)
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
    assert manifest["artifacts"]["lance"]["tables"] == {"chunks": 2}
    assert manifest["artifacts"]["dense_chunks"] == {
        "status": "ok",
        "sqlite_rows": 2,
        "lance_rows": 2,
        "unique_ids": 2,
        "embedding_dim": 1024,
    }


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([_dense_row(101)], "ID mismatch"),
        ([_dense_row(101), _dense_row(101), _dense_row(102)], "duplicates"),
        ([_dense_row(101, text="changed"), _dense_row(102)], "metadata mismatch"),
        (
            [_dense_row(101, embedding_size=3), _dense_row(102, embedding_size=3)],
            "invalid embedding",
        ),
    ],
)
def test_create_backup_rejects_dense_chunk_inconsistency(
    tmp_path: Path,
    rows: list[dict],
    message: str,
) -> None:
    source = tmp_path / "source"
    meta_db = source / "meta2.db"
    novel_db = source / "novel.db"
    lance_db = source / "novel.lancedb"
    _create_sqlite(meta_db, "meta")
    _create_novel_sqlite(novel_db)
    _create_lance(lance_db, rows)

    with pytest.raises(RuntimeError, match=message):
        create_backup(
            meta_db=meta_db,
            novel_db=novel_db,
            lance_db=lance_db,
            backup_dir=tmp_path / "backups",
            label="invalid-dense",
            retention_days=14,
        )

    assert not (tmp_path / "backups" / "invalid-dense").exists()


def test_restore_verification_rechecks_dense_chunks(tmp_path: Path) -> None:
    source = tmp_path / "source"
    meta_db = source / "meta2.db"
    novel_db = source / "novel.db"
    lance_db = source / "novel.lancedb"
    backup_dir = tmp_path / "backups"
    _create_sqlite(meta_db, "meta")
    _create_novel_sqlite(novel_db)
    _create_lance(lance_db)
    snapshot = create_backup(
        meta_db=meta_db,
        novel_db=novel_db,
        lance_db=lance_db,
        backup_dir=backup_dir,
        label="valid-dense",
        retention_days=14,
    )
    table = lancedb.connect(snapshot / "novel.lancedb").open_table("chunks")
    table.delete("chunk_id = 102")

    with pytest.raises(RuntimeError, match="ID mismatch"):
        verify_latest_backup(backup_dir=backup_dir, restore_test_dir=tmp_path / "restore-tests")


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
