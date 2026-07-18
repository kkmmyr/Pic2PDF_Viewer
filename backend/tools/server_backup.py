"""Linuxサーバー用の検証付きDBバックアップと復元試験。"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import config
from utils.atomic_json import atomic_write_json

_FORMAT_VERSION = 1
_LABEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


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
        if novel_db.is_file():
            artifacts["novel"] = _backup_sqlite(novel_db, staging_path / "novel.db")
        else:
            artifacts["novel"] = {"status": "not_present", "source": str(novel_db)}
        artifacts["lance"] = _backup_lance(lance_db, staging_path / "novel.lancedb")

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
        if artifacts["novel"]["status"] == "ok":
            checks["novel"] = _sqlite_integrity(restored / "novel.db")
        if artifacts["lance"]["status"] == "ok":
            checks["lance"] = _validate_lance(restored / "novel.lancedb")

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
        )
        print(f"verified backup created: {destination}")
    else:
        result = verify_latest_backup(backup_dir=args.backup_dir, restore_test_dir=args.restore_test_dir)
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
