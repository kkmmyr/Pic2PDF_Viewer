"""B-25: meta.db の OneDrive スナップショットバックアップ。

sqlite3.backup() でホットバックアップを作成し META_DB_BACKUP_DIR に保存する。
ファイル名: meta_YYYYMMDD_HHMMSS.db（タイムスタンプ付き）
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import services.meta_db as meta_db_module
from config import META_DB_BACKUP_DIR
from utils.logger import get_logger

logger = get_logger(__name__)


def backup_meta_db() -> dict:
    """meta.db を META_DB_BACKUP_DIR に sqlite3.backup() でスナップショット保存する。"""
    dest_dir = Path(META_DB_BACKUP_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)

    src_path = meta_db_module._db_path()
    dest_filename = f"meta_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    dest_path = dest_dir / dest_filename

    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(str(dest_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    size = dest_path.stat().st_size
    backed_up_at = datetime.now().isoformat()
    logger.info("meta.db backed up to %s (%d bytes)", dest_path, size)
    return {
        "path": str(dest_path),
        "size_bytes": size,
        "backed_up_at": backed_up_at,
    }


def get_backup_status() -> dict:
    """最新バックアップの情報を返す。"""
    backup_dir = Path(META_DB_BACKUP_DIR)
    if not backup_dir.exists():
        return {"last_backup": None, "backup_dir": str(backup_dir), "total_backups": 0}

    backups = sorted(backup_dir.glob("meta_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        return {"last_backup": None, "backup_dir": str(backup_dir), "total_backups": 0}

    latest = backups[0]
    return {
        "last_backup": {
            "path": str(latest),
            "size_bytes": latest.stat().st_size,
            "backed_up_at": datetime.fromtimestamp(latest.stat().st_mtime).isoformat(),
        },
        "backup_dir": str(backup_dir),
        "total_backups": len(backups),
    }
