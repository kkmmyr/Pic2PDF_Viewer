"""Linuxサーバー用の検証付きDBバックアップと復元試験。"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import sqlite3
import tempfile
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import config
from utils.atomic_json import atomic_write_json

_FORMAT_VERSION = 1
_LABEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_DENSE_EMBEDDING_DIM = 1024
_DENSE_METADATA_FIELDS = ("book_name", "page_no", "text", "char_count", "page_count")


def _sqlite_integrity(path: Path) -> str:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        rows = connection.execute("PRAGMA integrity_check").fetchall()
    finally:
        connection.close()
    result = "\n".join(str(row[0]) for row in rows)
    if result != "ok":
        raise RuntimeError(f"SQLite integrity_check failed for {path}: {result}")
    return result


def _backup_sqlite(source: Path, destination: Path) -> dict[str, Any]:
    if not source.is_file():
        raise FileNotFoundError(f"SQLite database not found: {source}")

    source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True, timeout=30.0)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()

    return {
        "status": "ok",
        "source": str(source),
        "file": destination.name,
        "bytes": destination.stat().st_size,
        "integrity_check": _sqlite_integrity(destination),
    }


def _validate_lance(path: Path) -> dict[str, int]:
    import lancedb

    database = lancedb.connect(path)
    table_names = sorted(database.list_tables(limit=10_000).tables)
    return {table_name: database.open_table(table_name).count_rows() for table_name in table_names}


def _sqlite_dense_chunks(path: Path) -> dict[int, tuple[str, int, str, int, int]] | None:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        has_chunks = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunks'").fetchone()
        if has_chunks is None:
            return None
        rows = connection.execute(
            """
            SELECT c.id, b.name, p.page_no, c.text, p.char_count, b.page_count
            FROM chunks c
            JOIN pages p ON p.id = c.page_id
            JOIN books b ON b.id = p.book_id
            ORDER BY c.id
            """
        ).fetchall()
    finally:
        connection.close()
    return {int(row[0]): (str(row[1]), int(row[2]), str(row[3]), int(row[4]), int(row[5])) for row in rows}


def _dense_error(message: str) -> RuntimeError:
    return RuntimeError(f"dense chunk cross-store validation failed: {message}")


def _validate_dense_chunks(novel_db: Path, lance_db: Path) -> dict[str, Any]:
    """SQLite chunksを正本としてLanceDBのID、metadata、vectorを全行検査する。"""
    expected = _sqlite_dense_chunks(novel_db)
    if expected is None:
        return {"status": "not_applicable", "reason": "sqlite_chunks_table_not_present"}

    if not lance_db.is_dir():
        if expected:
            raise _dense_error(f"LanceDB is missing for {len(expected)} SQLite rows")
        return {
            "status": "ok",
            "sqlite_rows": 0,
            "lance_rows": 0,
            "unique_ids": 0,
            "embedding_dim": _DENSE_EMBEDDING_DIM,
        }

    import lancedb

    database = lancedb.connect(lance_db)
    table_names = set(database.list_tables(limit=10_000).tables)
    if "chunks" not in table_names:
        if expected:
            raise _dense_error(f"LanceDB chunks table is missing for {len(expected)} SQLite rows")
        lance_rows: list[dict[str, Any]] = []
    else:
        table = database.open_table("chunks").to_arrow()
        required = {"chunk_id", *_DENSE_METADATA_FIELDS, "embedding"}
        missing_columns = sorted(required - set(table.column_names))
        if missing_columns:
            raise _dense_error(f"LanceDB chunks columns are missing: {missing_columns}")
        lance_rows = table.select(["chunk_id", *_DENSE_METADATA_FIELDS, "embedding"]).to_pylist()

    ids = [int(row["chunk_id"]) for row in lance_rows]
    duplicate_ids = sorted(chunk_id for chunk_id, count in Counter(ids).items() if count > 1)
    expected_ids = set(expected)
    actual_ids = set(ids)
    missing_ids = sorted(expected_ids - actual_ids)
    extra_ids = sorted(actual_ids - expected_ids)
    if missing_ids or extra_ids or duplicate_ids:
        raise _dense_error(
            f"ID mismatch: missing={missing_ids[:10]}, extra={extra_ids[:10]}, duplicates={duplicate_ids[:10]}"
        )

    metadata_mismatches: list[int] = []
    invalid_vectors: list[int] = []
    for row in lance_rows:
        chunk_id = int(row["chunk_id"])
        actual_metadata = (
            str(row["book_name"]),
            int(row["page_no"]),
            str(row["text"]),
            int(row["char_count"]),
            int(row["page_count"]),
        )
        if actual_metadata != expected[chunk_id]:
            metadata_mismatches.append(chunk_id)
        embedding = row["embedding"]
        if (
            not isinstance(embedding, list)
            or len(embedding) != _DENSE_EMBEDDING_DIM
            or not all(math.isfinite(float(value)) for value in embedding)
        ):
            invalid_vectors.append(chunk_id)
    if metadata_mismatches:
        raise _dense_error(f"metadata mismatch for chunk IDs {metadata_mismatches[:10]}")
    if invalid_vectors:
        raise _dense_error(f"invalid embedding for chunk IDs {invalid_vectors[:10]}")

    return {
        "status": "ok",
        "sqlite_rows": len(expected),
        "lance_rows": len(lance_rows),
        "unique_ids": len(actual_ids),
        "embedding_dim": _DENSE_EMBEDDING_DIM,
    }


def _directory_size(path: Path) -> int:
    return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())


def _backup_lance(source: Path, destination: Path) -> dict[str, Any]:
    if not source.is_dir():
        return {"status": "not_present", "source": str(source)}
    shutil.copytree(source, destination)
    return {
        "status": "ok",
        "source": str(source),
        "directory": destination.name,
        "bytes": _directory_size(destination),
        "tables": _validate_lance(destination),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())


def _load_manifest(snapshot: Path) -> dict[str, Any] | None:
    manifest_path = snapshot / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if manifest.get("format_version") != _FORMAT_VERSION:
        return None
    return manifest


def _purge_expired(backup_dir: Path, retention_days: int, now: datetime) -> list[str]:
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")
    threshold = now - timedelta(days=retention_days)
    removed: list[str] = []
    backup_root = backup_dir.resolve()
    for snapshot in backup_dir.iterdir():
        if not snapshot.is_dir() or snapshot.name.startswith("."):
            continue
        manifest = _load_manifest(snapshot)
        if manifest is None:
            continue
        try:
            created_at = datetime.fromisoformat(str(manifest["created_at"]))
        except (KeyError, TypeError, ValueError):
            continue
        resolved = snapshot.resolve()
        if created_at < threshold and resolved.parent == backup_root:
            shutil.rmtree(resolved)
            removed.append(snapshot.name)
    return removed


def create_backup(
    *,
    meta_db: Path,
    novel_db: Path,
    lance_db: Path,
    backup_dir: Path,
    label: str,
    retention_days: int,
    now: datetime | None = None,
    kindle_catalog_db: Path | None = None,
) -> Path:
    """全DBを一時世代へ保存・検査し、成功した世代だけ公開する。"""
    if not _LABEL_PATTERN.fullmatch(label):
        raise ValueError("label may contain only letters, digits, dot, underscore, and hyphen")
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    backup_dir.mkdir(parents=True, exist_ok=True)
    final_path = backup_dir / label
    if final_path.exists():
        raise FileExistsError(f"backup generation already exists: {final_path}")
    staging_path = Path(tempfile.mkdtemp(dir=backup_dir, prefix=f".{label}.tmp-"))
    try:
        artifacts: dict[str, Any] = {"meta2": _backup_sqlite(meta_db, staging_path / "meta2.db")}
        catalog_source = kindle_catalog_db or meta_db.parent / "kindle_catalog.db"
        if catalog_source.is_file():
            artifacts["kindle_catalog"] = _backup_sqlite(
                catalog_source,
                staging_path / "kindle_catalog.db",
            )
        else:
            artifacts["kindle_catalog"] = {
                "status": "not_present",
                "source": str(catalog_source),
            }
        if novel_db.is_file():
            artifacts["novel"] = _backup_sqlite(novel_db, staging_path / "novel.db")
        else:
            artifacts["novel"] = {"status": "not_present", "source": str(novel_db)}
        artifacts["lance"] = _backup_lance(lance_db, staging_path / "novel.lancedb")
        if artifacts["novel"]["status"] == "ok":
            artifacts["dense_chunks"] = _validate_dense_chunks(
                staging_path / "novel.db",
                staging_path / "novel.lancedb",
            )
        else:
            artifacts["dense_chunks"] = {"status": "not_applicable", "reason": "novel_not_present"}

        manifest = {
            "format_version": _FORMAT_VERSION,
            "created_at": current_time.astimezone(UTC).isoformat(),
            "label": label,
            "artifacts": artifacts,
        }
        _write_json(staging_path / "manifest.json", manifest)
        os.replace(staging_path, final_path)
    finally:
        if staging_path.exists():
            shutil.rmtree(staging_path)

    _purge_expired(backup_dir, retention_days, current_time)
    return final_path


def _latest_snapshot(backup_dir: Path) -> tuple[Path, dict[str, Any]]:
    candidates: list[tuple[datetime, Path, dict[str, Any]]] = []
    if not backup_dir.is_dir():
        raise FileNotFoundError(f"backup directory not found: {backup_dir}")
    for snapshot in backup_dir.iterdir():
        if not snapshot.is_dir() or snapshot.name.startswith("."):
            continue
        manifest = _load_manifest(snapshot)
        if manifest is None:
            continue
        try:
            created_at = datetime.fromisoformat(str(manifest["created_at"]))
        except (KeyError, TypeError, ValueError):
            continue
        candidates.append((created_at, snapshot, manifest))
    if not candidates:
        raise FileNotFoundError(f"no valid backup generation found in {backup_dir}")
    _, snapshot, manifest = max(candidates, key=lambda item: item[0])
    return snapshot, manifest


def verify_latest_backup(*, backup_dir: Path, restore_test_dir: Path) -> dict[str, Any]:
    """最新世代を別ディレクトリへ復元し、全成果物を再検査する。"""
    snapshot, manifest = _latest_snapshot(backup_dir)
    restore_test_dir.mkdir(parents=True, exist_ok=True)
    staging_path = Path(tempfile.mkdtemp(dir=restore_test_dir, prefix=f".{snapshot.name}.restore-"))
    restored = staging_path / snapshot.name
    try:
        shutil.copytree(snapshot, restored)
        checks: dict[str, Any] = {}
        artifacts = manifest["artifacts"]
        if artifacts["meta2"]["status"] == "ok":
            checks["meta2"] = _sqlite_integrity(restored / "meta2.db")
        if artifacts.get("kindle_catalog", {}).get("status") == "ok":
            checks["kindle_catalog"] = _sqlite_integrity(restored / "kindle_catalog.db")
        if artifacts["novel"]["status"] == "ok":
            checks["novel"] = _sqlite_integrity(restored / "novel.db")
        if artifacts["lance"]["status"] == "ok":
            checks["lance"] = _validate_lance(restored / "novel.lancedb")
        if artifacts["novel"]["status"] == "ok":
            checks["dense_chunks"] = _validate_dense_chunks(
                restored / "novel.db",
                restored / "novel.lancedb",
            )

        result = {
            "verified_at": datetime.now(UTC).isoformat(),
            "snapshot": snapshot.name,
            "checks": checks,
        }
        atomic_write_json(restore_test_dir / "last-success.json", result)
        return result
    finally:
        shutil.rmtree(staging_path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup_parser = subparsers.add_parser("backup", help="create a verified backup")
    backup_parser.add_argument("--label", default=datetime.now().strftime("%Y-%m-%d_%H%M%S"))
    backup_parser.add_argument("--meta-db", type=Path, default=Path(config.META_DB_DIR) / "meta2.db")
    backup_parser.add_argument(
        "--kindle-catalog-db",
        type=Path,
        default=Path(config.META_DB_DIR) / "kindle_catalog.db",
    )
    backup_parser.add_argument("--novel-db", type=Path, default=Path(config.NOVEL_DB_PATH))
    backup_parser.add_argument("--lance-db", type=Path, default=Path(config.NOVEL_DB_LANCE_PATH))
    backup_parser.add_argument("--backup-dir", type=Path, default=Path(config.SERVER_BACKUP_DIR))
    backup_parser.add_argument("--retention-days", type=int, default=config.SERVER_BACKUP_RETENTION_DAYS)

    verify_parser = subparsers.add_parser("verify-latest", help="restore and verify latest backup")
    verify_parser.add_argument("--backup-dir", type=Path, default=Path(config.SERVER_BACKUP_DIR))
    verify_parser.add_argument("--restore-test-dir", type=Path, default=Path(config.SERVER_RESTORE_TEST_DIR))
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "backup":
        destination = create_backup(
            meta_db=args.meta_db,
            novel_db=args.novel_db,
            lance_db=args.lance_db,
            backup_dir=args.backup_dir,
            label=args.label,
            retention_days=args.retention_days,
            kindle_catalog_db=args.kindle_catalog_db,
        )
        print(f"verified backup created: {destination}")
    else:
        result = verify_latest_backup(backup_dir=args.backup_dir, restore_test_dir=args.restore_test_dir)
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
