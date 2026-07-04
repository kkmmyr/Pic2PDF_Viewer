"""PDF 生成・変換ジョブルーター。

POST /generate          — バックグラウンドで PDF 生成ジョブを起動
GET  /generate/job/:id  — ジョブ進捗を取得
GET  /generate/watcher  — 同人誌フォルダ自動監視の状態を取得
GET  /status            — 入力ディレクトリ (config.DOUJIN_INPUT_DIR) の変換状態を一覧
POST /batch_compress    — 既存 PDF を一括圧縮

PDF 生成ジョブの実行ロジック・排他ロックは services.generate_service に集約し、
本ルーターの手動起動と services.doujin_watcher の自動起動が同一のコードパスを通る。
"""

import os
from enum import StrEnum

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import config
from routers._deps import log_and_raise_500
from routers.api_schemas import (
    BatchCompressResponse,
    GenerateJobOut,
    GenerateStartResponse,
    GenerateStatusResponse,
    GenerateWatcherResponse,
)
from services.doujin_watcher import doujin_watcher
from services.generate_service import get_active_job_id, job_store, start_generate_job
from services.pdf_generator import batch_compress
from utils.file_utils import is_webp_file, is_zip_file
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


class GenerateStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


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


@router.get("/status", response_model=GenerateStatusResponse)
def get_status():
    if not os.path.isdir(config.DOUJIN_INPUT_DIR):
        return {"items": []}

    current_item = job_store.get_active_current_item()
    items_status = []

    for root, _dirs, files in os.walk(config.DOUJIN_INPUT_DIR):
        webp_files = [f for f in files if is_webp_file(f)]
        if webp_files:
            folder_name = os.path.basename(root)
            if root == config.DOUJIN_INPUT_DIR:
                folder_name = os.path.basename(config.DOUJIN_INPUT_DIR)

            img_dir = os.path.join(config.IMAGES_DIR, folder_name)

            if current_item == folder_name:
                status = GenerateStatus.IN_PROGRESS
            elif os.path.isdir(img_dir) and os.listdir(img_dir):
                status = GenerateStatus.COMPLETED
            else:
                status = GenerateStatus.NOT_STARTED

            items_status.append({"name": folder_name, "type": "folder", "status": status})

        zip_files = [f for f in files if is_zip_file(f)]
        for zip_file in zip_files:
            item_name = os.path.splitext(zip_file)[0]

            img_dir = os.path.join(config.IMAGES_DIR, item_name)

            if current_item == item_name:
                status = GenerateStatus.IN_PROGRESS
            elif os.path.isdir(img_dir) and os.listdir(img_dir):
                status = GenerateStatus.COMPLETED
            else:
                status = GenerateStatus.NOT_STARTED

            items_status.append({"name": item_name, "type": "zip", "status": status})

    return {"items": items_status}


class BatchCompressRequest(BaseModel):
    quality: int = 50


@router.post("/batch_compress", response_model=BatchCompressResponse)
@log_and_raise_500("batch_compress")
def batch_compress_pdfs(request: BatchCompressRequest):
    if not os.path.exists(config.IMAGES_DIR):
        raise HTTPException(status_code=404, detail="Images directory not found")
    generated = batch_compress(config.IMAGES_DIR, config.PDF_COMPRESSED_DIR, request.quality)
    return {"message": "Batch compression complete", "files": generated}
