"""Exercise OCR publication backup against a genuinely full isolated filesystem."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from config import app_settings
from services.novel_db.ocr_publication_backup import create_verified_publication_backup


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _available_bytes(path: Path) -> int:
    values = os.statvfs(path)
    return values.f_bavail * values.f_frsize


def run_audit(root: Path) -> dict[str, object]:
    root = root.resolve()
    if not root.is_dir() or not os.path.ismount(root):
        raise ValueError("audit root must be an isolated mount point")
    if any(root.iterdir()):
        raise ValueError("audit root must be empty")
    novel_dir = root / "novel_db"
    backup_root = root / "ocr-publication-backups"
    novel_dir.mkdir(mode=0o700)
    backup_root.mkdir(mode=0o700)
    database = novel_dir / "novel.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE payload (id INTEGER PRIMARY KEY, data BLOB NOT NULL)")
        connection.execute("INSERT INTO payload(data) VALUES (zeroblob(3000000))")
        connection.commit()
    finally:
        connection.close()
    before = _sha256(database)
    filler = root / "filler.bin"
    reserve_bytes = 128 * 1024
    with filler.open("wb") as stream:
        block = b"\0" * (64 * 1024)
        while _available_bytes(root) > reserve_bytes + len(block):
            stream.write(block)
        stream.flush()
        os.fsync(stream.fileno())

    original_dir = app_settings.NOVEL_DB_DIR
    failure: BaseException | None = None
    try:
        app_settings.NOVEL_DB_DIR = novel_dir
        create_verified_publication_backup(1, "publish")
    except (OSError, sqlite3.Error) as exc:
        failure = exc
    finally:
        app_settings.NOVEL_DB_DIR = original_dir

    restored = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        integrity = str(restored.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        restored.close()
    generations = [path.name for path in backup_root.iterdir()]
    result: dict[str, object] = {
        "passed": failure is not None and before == _sha256(database) and integrity == "ok" and not generations,
        "failure_type": type(failure).__name__ if failure is not None else None,
        "canonical_sha256_unchanged": before == _sha256(database),
        "canonical_integrity_check": integrity,
        "published_generation_count": len(generations),
        "available_bytes_at_failure": _available_bytes(root),
    }
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_audit(args.root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
