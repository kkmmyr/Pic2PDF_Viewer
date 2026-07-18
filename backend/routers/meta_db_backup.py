"""B-25: meta2.db バックアップ API。"""

from fastapi import APIRouter

from routers.api_schemas import BackupStatusResponse, BackupTriggeredResponse
from services.meta_db_backup import backup_meta_db, get_backup_status

router = APIRouter()


@router.post("/meta_db/backup", response_model=BackupTriggeredResponse)
def trigger_backup() -> dict:
    """meta2.db を OneDrive にスナップショットバックアップする。"""
    return backup_meta_db()


@router.get("/meta_db/backup/status", response_model=BackupStatusResponse)
def backup_status() -> dict:
    """最新バックアップの情報を返す。"""
    return get_backup_status()
