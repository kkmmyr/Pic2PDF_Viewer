"""PDF 生成・変換ジョブルーター。

POST /generate          — バックグラウンドで PDF 生成ジョブを起動
GET  /generate/job/:id  — ジョブ進捗を取得
GET  /generate/watcher  — 同人誌フォルダ自動監視の状態を取得

PDF 生成ジョブの実行ロジック・排他ロックは services.generate_service に集約し、
本ルーターの手動起動と services.doujin_watcher の自動起動が同一のコードパスを通る。
"""

import os

from fastapi import APIRouter, HTTPException

import config
from routers.api_schemas import (
    GenerateJobOut,
    GenerateStartResponse,
    GenerateWatcherResponse,
)
from services.doujin_watcher import doujin_watcher
from services.generate_service import get_active_job_id, job_store, start_generate_job
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.post("/generate", response_model=GenerateStartResponse)
async def generate_pdfs():
    if not os.path.isdir(config.DOUJIN_INPUT_DIR):
        raise HTTPException(status_code=503, detail=f"Input directory not found: {config.DOUJIN_INPUT_DIR}")

    job = await start_generate_job(trigger="manual")
    if job is None:
        active_job_id = get_active_job_id()
        raise HTTPException(status_code=409, detail=f"Generation already running (job_id={active_job_id})")

    # 手動実行 = 再試行の意思表示。同一残骸に対する自動再試行のブロックを解除する。
    doujin_watcher.clear_last_attempted()

    return {"job_id": job.job_id, "status": "pending"}


@router.get("/generate/watcher", response_model=GenerateWatcherResponse)
def get_generate_watcher():
    """同人誌フォルダ自動監視の現在状態を返す。"""
    return {
        "enabled": config.DOUJIN_WATCH_ENABLED,
        "state": doujin_watcher.state,
        "interval_sec": config.DOUJIN_WATCH_INTERVAL_SEC,
        "last_scan_at": doujin_watcher.last_scan_at,
        "pending_items": [{"name": p.name, "kind": p.kind} for p in doujin_watcher.pending_items],
        "active_job_id": get_active_job_id(),
        "last_auto_job": doujin_watcher.last_auto_job,
        "retry_blocked": doujin_watcher.retry_blocked,
    }


@router.get("/generate/job/{job_id}", response_model=GenerateJobOut)
def get_generate_job(job_id: str):
    """ジョブの進捗・結果を取得する。"""
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()
