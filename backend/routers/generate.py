"""PDF 生成・変換ジョブルーター。

POST /generate         — バックグラウンドで PDF 生成ジョブを起動
GET  /generate/job/:id — ジョブ進捗を取得
GET  /status           — 入力ディレクトリ (config.DOUJIN_INPUT_DIR) の変換状態を一覧
POST /batch_compress   — 既存 PDF を一括圧縮
"""

import asyncio
import os
from enum import StrEnum

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import config
from routers._deps import log_and_raise_500
from routers.api_schemas import BatchCompressResponse, GenerateJobOut, GenerateStartResponse, GenerateStatusResponse
from services.job_manager import GenerateJob, JobStatus, JobStore
from services.meta_store import update_meta_locked
from services.pdf_generator import batch_compress, scan_and_generate
from utils.file_utils import is_webp_file, is_zip_file
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


class GenerateStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


job_store = JobStore()


def _run_generate_job(job: GenerateJob) -> None:
    """同期ワーカー: executor スレッドで PDF 生成ジョブを実行する。"""

    def progress_callback(item_name: str):
        job.update(current_item=item_name)
        logger.info("Processing: %s", item_name)

    try:
        job.update(status=JobStatus.RUNNING, current_item="Starting...")

        result = scan_and_generate(
            config.DOUJIN_INPUT_DIR,
            None,  # image-only モード: PDF 生成をスキップ
            config.THUMBNAIL_DIR,
            config.IMAGES_DIR,
            config.COMPLETE_DIR,
            progress_callback=progress_callback,
        )

        # 新規生成ファイルにのみ genre: "オリジナル" を初期書き込み（再生成時は保持）
        if result.generated:

            def _init_genre(data):
                for name in result.generated:
                    if name not in data:
                        data[name] = {"genre": "オリジナル"}

            update_meta_locked("doujin", _init_genre)

        failed_dicts = [{"name": n, "error": e} for n, e in result.failed_items]
        if failed_dicts:
            message = f"Generation complete: {len(result.generated)} succeeded, {len(failed_dicts)} failed"
        else:
            message = "Generation complete"

        job.update(
            status=JobStatus.COMPLETED,
            current_item=None,
            files=result.generated,
            failed_items=failed_dicts,
            message=message,
        )
        logger.info("Job %s completed: %d files, %d failed", job.job_id, len(result.generated), len(failed_dicts))

    except Exception as e:
        logger.exception("Job %s failed", job.job_id)
        job.update(status=JobStatus.FAILED, current_item=None, error=str(e))


async def _run_generate_job_async(job: GenerateJob) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _run_generate_job, job)


@router.post("/generate", response_model=GenerateStartResponse)
async def generate_pdfs():
    if not os.path.isdir(config.DOUJIN_INPUT_DIR):
        raise HTTPException(status_code=503, detail=f"Input directory not found: {config.DOUJIN_INPUT_DIR}")

    job = job_store.create()
    asyncio.create_task(_run_generate_job_async(job))

    return {"job_id": job.job_id, "status": "pending"}


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
