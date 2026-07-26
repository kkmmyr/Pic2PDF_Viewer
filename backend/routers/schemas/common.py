"""複数機能から利用する管理系APIのレスポンススキーマ。"""

from pydantic import BaseModel


class BackupTriggeredResponse(BaseModel):
    path: str
    size_bytes: int
    backed_up_at: str


class BackupStatusResponse(BaseModel):
    last_backup: dict | None = None
    backup_dir: str | None = None
    total_backups: int
