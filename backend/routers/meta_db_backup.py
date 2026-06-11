"""B-25: meta.db バックアップ API。"""

from fastapi import APIRouter

from services.meta_db_backup import backup_meta_db, get_backup_status

router = APIRouter()


@router.post("/meta_db/backup")
def trigger_backup() -> dict:
    """meta.db を OneDrive にスナップショットバックアップする。"""
    return backup_meta_db()


@router.get("/meta_db/backup/status")
def backup_status() -> dict:
    """最新バックアップの情報を返す。"""
    return get_backup_status()
