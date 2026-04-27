from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from enum import Enum
import os
import threading

import fitz

from services.pdf_service import PdfService
from services.thumbnail_service import ThumbnailService
from services.pdf_generator import scan_and_generate, batch_compress
from services.job_manager import GenerateJob, JobStore, JobStatus
from config import (
    get_dirs_by_source,
    PDF_DIR, THUMBNAIL_DIR, IMAGES_DIR, COMPLETE_DIR, PDF_COMPRESSED_DIR,
)
from utils.path_utils import validate_safe_path, validate_safe_name
from utils.file_utils import is_webp_file, is_zip_file, is_pdf_file
from utils.file_naming import get_thumbnail_name
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
    generate_compressed: bool = False
    quality: int = 50


def _run_generate_job(job: GenerateJob, request: GenerateRequest) -> None:
    """バックグラウンドスレッドでPDF生成を実行する。"""
    def progress_callback(item_name: str):
        job.update(current_item=item_name)
        logger.info("Processing: %s", item_name)

    try:
        job.update(status=JobStatus.RUNNING, current_item="Starting...")

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

            pdf_path = os.path.join(PDF_DIR, f"{folder_name}.pdf")

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
            thumb_name = get_thumbnail_name(filename)
            target_thumb_dir = os.path.join(base_thumb_dir, path)
            thumb_path = os.path.join(target_thumb_dir, thumb_name)
            ThumbnailService.generate_thumbnail(pdf_path, thumb_path)
            logger.info("Regenerated thumbnail: %s", thumb_path)

        return {"message": "Pages deleted successfully", "total_pages": new_total}

    except Exception as e:
        logger.exception("delete_pages failed: %s", filename)
        raise HTTPException(status_code=500, detail=str(e))


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


# ---------------------------------------------------------------------------
# PDF 結合（複数の PDF を順番に結合して新しい PDF を生成）
# ---------------------------------------------------------------------------

class MergePdfsRequest(BaseModel):
    names: list[str]   # 結合対象の .pdf ファイル名リスト（順序通りに結合）
    output_name: str   # 出力ファイル名（.pdf 拡張子付き）
    path: str = ""
    source: str = "generated"


@router.post("/pdfs/merge")
def merge_pdfs(request: MergePdfsRequest):
    """複数の PDF を順番に結合して新しい PDF を生成する。"""
    validate_safe_path(request.path, param_name="path")
    validate_safe_name(request.output_name, param_name="output_name")
    for name in request.names:
        validate_safe_name(name, param_name="name")

    if len(request.names) < 2:
        raise HTTPException(status_code=400, detail="At least 2 PDFs are required for merging")

    if not is_pdf_file(request.output_name):
        raise HTTPException(status_code=400, detail="output_name must end with .pdf")

    dirs = get_dirs_by_source(request.source)
    base_pdf_dir = dirs["pdf"]
    base_thumb_dir = dirs["thumb"]

    output_path = os.path.join(base_pdf_dir, request.path, request.output_name)
    if os.path.exists(output_path):
        raise HTTPException(status_code=400, detail="Output file already exists")

    merged_doc = None
    try:
        merged_doc = fitz.open()
        for name in request.names:
            pdf_path = os.path.join(base_pdf_dir, request.path, name)
            if not os.path.exists(pdf_path):
                raise HTTPException(status_code=404, detail=f"PDF not found: {name}")
            with fitz.open(pdf_path) as src:
                merged_doc.insert_pdf(src)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        merged_doc.save(output_path)
        total_pages = len(merged_doc)
        logger.info("Merged %d PDFs into %s (%d pages)", len(request.names), output_path, total_pages)
    finally:
        if merged_doc:
            merged_doc.close()

    # サムネイル生成
    thumb_name = get_thumbnail_name(request.output_name)
    thumb_path = os.path.join(base_thumb_dir, request.path, thumb_name)
    ThumbnailService.generate_thumbnail(output_path, thumb_path)

    return {"message": "PDFs merged successfully", "output_name": request.output_name, "total_pages": total_pages}
