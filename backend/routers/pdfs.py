from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from enum import Enum
import os
import threading
import uuid
from typing import Optional
from services.pdf_service import PdfService
from services.thumbnail_service import ThumbnailService
from services.pdf_generator import scan_and_generate
from config import get_dirs_by_source, PDF_DIR, THUMBNAIL_DIR, IMAGES_DIR, COMPLETE_DIR, PDF_COMPRESSED_DIR
from utils.path_utils import validate_safe_path
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


class GenerateStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


# ---------------------------------------------------------------------------
# ジョブ管理: 非同期PDF生成用
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class GenerateJob:
    """1回のPDF生成ジョブを表すデータクラス。"""
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.status: JobStatus = JobStatus.PENDING
        self.current_item: Optional[str] = None
        self.files: list[str] = []
        self.message: str = ""
        self.error: Optional[str] = None
        self._lock = threading.Lock()

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "job_id": self.job_id,
                "status": self.status.value,
                "current_item": self.current_item,
                "files": list(self.files),
                "message": self.message,
                "error": self.error,
            }

    def update(self, **kwargs) -> None:
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)


class JobStore:
    """実行中・完了済みジョブを保持するスレッドセーフなストア。"""
    _MAX_JOBS = 20  # 古いジョブを自動削除する上限

    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: dict[str, GenerateJob] = {}
        self._order: list[str] = []

    def create(self) -> GenerateJob:
        job = GenerateJob(str(uuid.uuid4()))
        with self._lock:
            self._jobs[job.job_id] = job
            self._order.append(job.job_id)
            # 古いジョブを削除
            while len(self._order) > self._MAX_JOBS:
                old_id = self._order.pop(0)
                self._jobs.pop(old_id, None)
        return job

    def get(self, job_id: str) -> Optional[GenerateJob]:
        with self._lock:
            return self._jobs.get(job_id)


job_store = JobStore()


class GenerateState:
    """PDF生成の進捗状態を管理するスレッドセーフなシングルトンクラス。
    (後方互換: /api/status エンドポイントで使用)"""
    _instance = None
    _class_lock = threading.Lock()

    def __new__(cls):
        with cls._class_lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._lock = threading.Lock()
                instance._current_item: Optional[str] = None
                cls._instance = instance
        return cls._instance

    def set_current_item(self, item: Optional[str]) -> None:
        with self._lock:
            self._current_item = item

    def get_current_item(self) -> Optional[str]:
        with self._lock:
            return self._current_item


generate_state = GenerateState()


class GenerateRequest(BaseModel):
    source_dir: str
    generate_compressed: bool = False
    quality: int = 50


def _run_generate_job(job: GenerateJob, request: GenerateRequest) -> None:
    """バックグラウンドスレッドでPDF生成を実行する。"""
    def progress_callback(item_name: str):
        job.update(current_item=item_name)
        generate_state.set_current_item(item_name)
        logger.info("Processing: %s", item_name)

    try:
        job.update(status=JobStatus.RUNNING, current_item="Starting...")
        generate_state.set_current_item("Starting...")

        compressed_dir = PDF_COMPRESSED_DIR if request.generate_compressed else None
        quality = request.quality if request.generate_compressed else None

        generated = scan_and_generate(
            request.source_dir,
            PDF_DIR,
            THUMBNAIL_DIR,
            IMAGES_DIR,
            COMPLETE_DIR,
            compressed_output_dir=compressed_dir,
            quality=quality,
            progress_callback=progress_callback,
        )
        job.update(
            status=JobStatus.COMPLETED,
            current_item=None,
            files=generated,
            message="Generation complete",
        )
        generate_state.set_current_item(None)
        logger.info("Job %s completed: %d files", job.job_id, len(generated))
    except Exception as e:
        job.update(status=JobStatus.FAILED, current_item=None, error=str(e))
        generate_state.set_current_item(None)
        logger.error("Job %s failed: %s", job.job_id, e)


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

    current_item = generate_state.get_current_item()
    items_status = []

    for root, dirs, files in os.walk(source_dir):
        webp_files = [f for f in files if f.lower().endswith('.webp')]
        if webp_files:
            folder_name = os.path.basename(root)
            if root == source_dir:
                folder_name = os.path.basename(source_dir)

            pdf_path = os.path.join(PDF_DIR, f"{folder_name}.pdf")

            if current_item == folder_name:
                status = GenerateStatus.IN_PROGRESS
            elif os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                status = GenerateStatus.COMPLETED
            else:
                status = GenerateStatus.NOT_STARTED

            items_status.append({"name": folder_name, "type": "folder", "status": status})

        zip_files = [f for f in files if f.lower().endswith('.zip')]
        for zip_file in zip_files:
            item_name = os.path.splitext(zip_file)[0]

            pdf_path = os.path.join(PDF_DIR, f"{item_name}.pdf")

            if current_item == item_name:
                status = GenerateStatus.IN_PROGRESS
            elif os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                status = GenerateStatus.COMPLETED
            else:
                status = GenerateStatus.NOT_STARTED

            items_status.append({"name": item_name, "type": "zip", "status": status})

    return {"items": items_status}

class DeletePagesRequest(BaseModel):
    page_indices: list[int]

@router.post("/pdfs/{filename}/delete_pages")
def delete_pages(filename: str, request: DeletePagesRequest, path: str = "", source: str = "generated"):
    validate_safe_path(path)

    dirs = get_dirs_by_source(source)
    base_pdf_dir = dirs["pdf"]
    base_thumb_dir = dirs["thumb"]

    target_pdf_dir = os.path.join(base_pdf_dir, path)
    pdf_path = os.path.join(target_pdf_dir, filename)

    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="File not found")

    try:
        new_total = PdfService.delete_pages(pdf_path, request.page_indices)

        if new_total > 0:
            thumb_name = os.path.splitext(filename)[0] + ".jpg"
            target_thumb_dir = os.path.join(base_thumb_dir, path)
            thumb_path = os.path.join(target_thumb_dir, thumb_name)
            ThumbnailService.generate_thumbnail(pdf_path, thumb_path)
            logger.info("Regenerated thumbnail: %s", thumb_path)

        return {"message": "Pages deleted successfully", "total_pages": new_total}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class BatchCompressRequest(BaseModel):
    quality: int = 50

@router.post("/batch_compress")
def batch_compress_pdfs(request: BatchCompressRequest):
    if not os.path.exists(IMAGES_DIR):
        raise HTTPException(status_code=404, detail="Images directory not found")

    generated = []
    try:
        from natsort import natsorted
        from services.pdf_generator import PdfGenerator

        for root, dirs, files in os.walk(IMAGES_DIR):
            webp_files = [f for f in files if f.lower().endswith('.webp')]
            if not webp_files:
                continue

            rel_path = os.path.relpath(root, IMAGES_DIR)
            folder_name = os.path.basename(root)

            generate_state.set_current_item(f"Batch: {rel_path}")
            logger.info("Processing folder: %s", rel_path)

            webp_files = natsorted(webp_files)
            image_paths = [os.path.join(root, f) for f in webp_files]

            pdf_filename = f"{folder_name}.pdf"

            if rel_path == ".":
                target_output_dir = PDF_COMPRESSED_DIR
            else:
                target_output_dir = os.path.join(PDF_COMPRESSED_DIR, os.path.dirname(rel_path))

            os.makedirs(target_output_dir, exist_ok=True)
            output_path = os.path.join(target_output_dir, pdf_filename)

            if os.path.exists(output_path):
                logger.info("Skipping already compressed: %s", output_path)
                continue

            generator = PdfGenerator(PDF_DIR, THUMBNAIL_DIR, IMAGES_DIR, COMPLETE_DIR, PDF_COMPRESSED_DIR, request.quality)
            generator._create_pdf_file(image_paths, output_path, quality=request.quality)

            generated.append(os.path.join(rel_path, pdf_filename) if rel_path != "." else pdf_filename)
            logger.info("Batch compressed: %s", output_path)

        generate_state.set_current_item(None)
        return {"message": "Batch compression complete", "files": generated}
    except Exception as e:
        generate_state.set_current_item(None)
        raise HTTPException(status_code=500, detail=str(e))
