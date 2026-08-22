"""Verified SQLite Online Backup before OCR publication changes."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from config import app_settings

PublicationOperation = Literal["publish", "rollback"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())


def create_verified_publication_backup(run_id: int, operation: PublicationOperation) -> str:
    """Create and verify a pre-operation backup, then atomically publish its generation."""
    if run_id < 1:
        raise ValueError("run_id must be positive")
    source_path = app_settings.NOVEL_DB_DIR / "novel.db"
    if not source_path.is_file():
        raise FileNotFoundError(f"novel database not found: {source_path}")

    backup_root = app_settings.NOVEL_DB_DIR.parent / "ocr-publication-backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(UTC)
    label = f"{created_at.strftime('%Y%m%dT%H%M%S.%fZ')}-{operation}-run-{run_id}-{uuid4().hex[:12]}"
    final_path = backup_root / label
    staging_path = Path(tempfile.mkdtemp(dir=backup_root, prefix=f".{label}.tmp-"))
    backup_path = staging_path / "novel.db"
    try:
        source = sqlite3.connect(f"{source_path.resolve().as_uri()}?mode=ro", uri=True, timeout=30)
        destination = sqlite3.connect(backup_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()

        restored = sqlite3.connect(f"{backup_path.resolve().as_uri()}?mode=ro", uri=True)
        try:
            integrity_rows = restored.execute("PRAGMA integrity_check").fetchall()
        finally:
            restored.close()
        integrity = "\n".join(str(row[0]) for row in integrity_rows)
        if integrity != "ok":
            raise RuntimeError(f"OCR publication backup integrity_check failed: {integrity}")

        manifest: dict[str, object] = {
            "format_version": 1,
            "created_at": created_at.isoformat(),
            "operation": operation,
            "run_id": run_id,
            "source": str(source_path),
            "database": backup_path.name,
            "bytes": backup_path.stat().st_size,
            "sha256": _sha256(backup_path),
            "integrity_check": integrity,
        }
        _write_manifest(staging_path / "manifest.json", manifest)
        os.replace(staging_path, final_path)
        return str(final_path)
    finally:
        if staging_path.exists():
            shutil.rmtree(staging_path)


def append_backup_reference(note: str | None, backup_reference: str) -> str:
    """Append the verified generation without discarding an operator note."""
    suffix = f"verified backup={backup_reference}"
    return suffix if not note else f"{note}; {suffix}"
