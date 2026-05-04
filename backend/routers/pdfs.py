"""PDF 操作ルーター（ページ削除・結合）。

generate/status/batch_compress は routers/generate.py に分離済み。
"""
import os

import fitz
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import get_dirs_by_source
from routers._deps import validate_request_targets, log_and_raise_500
from services.pdf_service import PdfService
from services.thumbnail_service import ThumbnailService
from utils.file_utils import is_pdf_file
from utils.file_naming import get_thumbnail_name
from utils.logger import get_logger
from utils.path_utils import validate_safe_path, validate_safe_name

logger = get_logger(__name__)

router = APIRouter()


class DeletePagesRequest(BaseModel):
    page_indices: list[int]


@router.post("/pdfs/{filename}/delete_pages")
@log_and_raise_500("delete_pages")
def delete_pages(filename: str, request: DeletePagesRequest, path: str = "", source: str = "generated"):
    validate_safe_path(path)

    dirs = get_dirs_by_source(source)
    base_pdf_dir = dirs["pdf"]
    base_thumb_dir = dirs["thumb"]

    target_pdf_dir = os.path.join(base_pdf_dir, path)
    pdf_path = os.path.join(target_pdf_dir, filename)

    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="File not found")

    new_total = PdfService.delete_pages(pdf_path, request.page_indices)

    if new_total > 0:
        thumb_name = get_thumbnail_name(filename)
        target_thumb_dir = os.path.join(base_thumb_dir, path)
        thumb_path = os.path.join(target_thumb_dir, thumb_name)
        ThumbnailService.generate_thumbnail(pdf_path, thumb_path)
        logger.info("Regenerated thumbnail: %s", thumb_path)

    return {"message": "Pages deleted successfully", "total_pages": new_total}


class MergePdfsRequest(BaseModel):
    names: list[str]   # 結合対象の .pdf ファイル名リスト（順序通りに結合）
    output_name: str   # 出力ファイル名（.pdf 拡張子付き）
    path: str = ""
    source: str = "generated"


@router.post("/pdfs/merge")
def merge_pdfs(request: MergePdfsRequest):
    """複数の PDF を順番に結合して新しい PDF を生成する。"""
    validate_request_targets(request.path, request.names)
    validate_safe_name(request.output_name, param_name="output_name")

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

    thumb_name = get_thumbnail_name(request.output_name)
    thumb_path = os.path.join(base_thumb_dir, request.path, thumb_name)
    ThumbnailService.generate_thumbnail(output_path, thumb_path)

    return {"message": "PDFs merged successfully", "output_name": request.output_name, "total_pages": total_pages}
