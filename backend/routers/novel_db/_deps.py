"""novel_db ルーター専用 FastAPI 依存関数。"""

from fastapi import HTTPException

from services.novel_db.job_queue import job_queue


def require_not_locked() -> None:
    """再構築ジョブ実行中なら 503 を返す共通チェック。Depends() で注入する。"""
    if job_queue.is_running:
        raise HTTPException(
            status_code=503,
            detail="rebuild is in progress",
            headers={"Retry-After": "10"},
        )
