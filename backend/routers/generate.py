"""PDF 生成・変換ジョブルーター。

POST /generate         — バックグラウンドで PDF 生成ジョブを起動
GET  /generate/job/:id — ジョブ進捗を取得
GET  /status           — ソースディレクトリの変換状態を一覧
POST /batch_compress   — 既存 PDF を一括圧縮
"""
import os
import threading
from enum import Enum

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import (
    PDF_COMPRESSED_DIR, THUMBNAIL_DIR, IMAGES_DIR, COMPLETE_DIR,
)
from services.job_manager import GenerateJob, JobStore, JobStatus
from services.meta_store import update_meta_locked
from services.pdf_generator import scan_and_generate, batch_compress
from utils.file_utils import is_webp_file, is_zip_file
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


class GenerateStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


job_store = JobStore()


class GenerateRequest(BaseModel):
    source_dir: str


def _run_generate_job(job: GenerateJob, request: GenerateRequest) -> None:
    """Background thread: PDF generation job."""
    def progress_callback(item_name: str):
        job.update(current_item=item_name)
        logger.info("Processing: %s", item_name)

    try:
        job.update(status=JobStatus.RUNNING, current_item="Starting...")

        generated = scan_and_generate(
            request.source_dir,
            PDF_COMPRESSED_DIR,
            THUMBNAIL_DIR,
            IMAGES_DIR,
            COMPLETE_DIR,
            progress_callback=progress_callback,
        )

        # 新規生成ファイルにのみ genre: "オリジナル" を初期書き込み（再生成時は保持）
        if generated:
            def _init_genre(data):
                for name in generated:
                    if name not in data:
                        data[name] = {"genre": "オリジナル"}
            update_meta_locked("generated", _init_genre)

        job.update(
            status=JobStatus.COMPLETED,
            current_item=None,
            files=generated,
            message="Generation complete",
        )
        logger.info("Job %s completed: %d files", job.job_id, len(generated))
    except Exception as e:
        logger.exception("Job %s failed", job.job_id)
        job.update(status=JobStatus.FAILED, current_item=None, error=str(e))


@router.post("/generate")
def generate_pdfs(request: GenerateRequest):
    if not os.path.isdir(request.source_dir):
        raise HTTPException(status_code=400, detail="Invalid directory path")

    job = job_store.create()
    t = threading.Thread(target=_run_generate_job, args=(job, request), daemon=True)
    t.start()

    return {"job_id": job.job_id, "status": "pending"}


@router.get("/generate/job/{job_id}")
def get_generate_job(job_id: str):
    """ジョブの進捗・結果を取得する。"""
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@router.get("/status")
def get_status(source_dir: str):
    if not os.path.isdir(source_dir):
        return {"items": []}

    current_item = job_store.get_active_current_item()
    items_status = []

    for root, dirs, files in os.walk(source_dir):
        webp_files = [f for f in files if is_webp_file(f)]
        if webp_files:
            folder_name = os.path.basename(root)
            if root == source_dir:
                folder_name = os.path.basename(source_dir)

            pdf_path = os.path.join(PDF_COMPRESSED_DIR, f"{folder_name}.pdf")

            if current_item == folder_name:
                status = GenerateStatus.IN_PROGRESS
            elif os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                status = GenerateStatus.COMPLETED
            else:
                status = GenerateStatus.NOT_STARTED

            items_status.append({"name": folder_name, "type": "folder", "status": status})

        zip_files = [f for f in files if is_zip_file(f)]
        for zip_file in zip_files:
            item_name = os.path.splitext(zip_file)[0]

            pdf_path = os.path.join(PDF_COMPRESSED_DIR, f"{item_name}.pdf")

            if current_item == item_name:
                status = GenerateStatus.IN_PROGRESS
            elif os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                status = GenerateStatus.COMPLETED
            else:
                status = GenerateStatus.NOT_STARTED

            items_status.append({"name": item_name, "type": "zip", "status": status})

    return {"items": items_status}


class BatchCompressRequest(BaseModel):
    quality: int = 50


@router.post("/batch_compress")
def batch_compress_pdfs(request: BatchCompressRequest):
    if not os.path.exists(IMAGES_DIR):
        raise HTTPException(status_code=404, detail="Images directory not found")

    try:
        generated = batch_compress(IMAGES_DIR, PDF_COMPRESSED_DIR, request.quality)
        return {"message": "Batch compression complete", "files": generated}
    except Exception as e:
        logger.exception("batch_compress failed")
        raise HTTPException(status_code=500, detail=str(e))
