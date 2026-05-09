"""PDF 操作ルーター（ページ削除・結合）。

generate/status/batch_compress は routers/generate.py に分離済み。
"""
import os

import fitz
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from config import get_dirs_by_source
from routers._deps import assert_valid_source, log_and_raise_500, validate_request_targets, validated_source
from services.image_service import (
    delete_book_image_pages,
    list_book_images,
    reorder_book_image_pages,
)
from services.pdf_generator import generate_thumbnail as generate_thumbnail_from_image
from services.pdf_service import PdfService
from services.thumbnail_service import ThumbnailService
from utils.file_naming import get_thumbnail_name
from utils.file_utils import is_pdf_file
from utils.logger import get_logger
from utils.path_utils import validate_safe_name, validate_safe_path

logger = get_logger(__name__)

router = APIRouter()


class DeletePagesRequest(BaseModel):
    page_indices: list[int]


class ReorderPagesRequest(BaseModel):
    page_indices: list[int]


def _validate_permutation(page_indices: list[int], total_pages: int) -> None:
    """`page_indices` が `[0..total_pages-1]` の完全なパーミュテーションかチェックして
    違反時は HTTP 400 を投げる。"""
    if sorted(page_indices) != list(range(total_pages)):
        raise HTTPException(
            status_code=400,
            detail=f"page_indices must be a permutation of [0..{total_pages - 1}]",
        )


@router.post("/pdfs/{filename}/delete_pages")
@log_and_raise_500("delete_pages")
def delete_pages(filename: str, request: DeletePagesRequest, path: str = "", source: str = Depends(validated_source)):
    validate_safe_path(path)
    validate_safe_name(filename)

    dirs = get_dirs_by_source(source)
    base_thumb_dir = dirs["thumb"]
    thumb_name = get_thumbnail_name(filename)
    thumb_path = os.path.join(base_thumb_dir, path, thumb_name) if path else os.path.join(base_thumb_dir, thumb_name)

    # generated は image-only モード: images/{book_name}/ から WebP を削除する
    if source == "generated":
        book_name = os.path.splitext(filename)[0]
        base_img_dir = dirs["img"]
        book_img_dir = os.path.join(base_img_dir, path, book_name) if path else os.path.join(base_img_dir, book_name)
        if not os.path.isdir(book_img_dir):
            raise HTTPException(status_code=404, detail="File not found")

        new_total = delete_book_image_pages(book_img_dir, request.page_indices)

        # 表紙が削除された可能性があるため、削除後の先頭 WebP から PIL ベースで再生成
        if new_total > 0:
            webps = list_book_images(base_img_dir, book_name, path)
            if webps:
                generate_thumbnail_from_image(webps[0], thumb_path)
                logger.info("Regenerated thumbnail: %s", thumb_path)

        return {"message": "Pages deleted successfully", "total_pages": new_total}

    # kindle / novel: 従来通り PDF から fitz でページ削除
    base_pdf_dir = dirs["pdf"]
    pdf_path = os.path.join(base_pdf_dir, path, filename) if path else os.path.join(base_pdf_dir, filename)

    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="File not found")

    new_total = PdfService.delete_pages(pdf_path, request.page_indices)

    if new_total > 0:
        ThumbnailService.generate_thumbnail(pdf_path, thumb_path)
        logger.info("Regenerated thumbnail: %s", thumb_path)

    return {"message": "Pages deleted successfully", "total_pages": new_total}


@router.post("/pdfs/{filename}/reorder_pages")
@log_and_raise_500("reorder_pages")
def reorder_pages(filename: str, request: ReorderPagesRequest, path: str = "", source: str = Depends(validated_source)):
    validate_safe_path(path)
    validate_safe_name(filename)

    dirs = get_dirs_by_source(source)
    base_thumb_dir = dirs["thumb"]
    thumb_name = get_thumbnail_name(filename)
    thumb_path = os.path.join(base_thumb_dir, path, thumb_name) if path else os.path.join(base_thumb_dir, thumb_name)

    # generated は image-only モード: images/{book_name}/ の WebP を再採番リネーム
    if source == "generated":
        book_name = os.path.splitext(filename)[0]
        base_img_dir = dirs["img"]
        book_img_dir = os.path.join(base_img_dir, path, book_name) if path else os.path.join(base_img_dir, book_name)
        if not os.path.isdir(book_img_dir):
            raise HTTPException(status_code=404, detail="File not found")

        # 現在のページ数を取って先にバリデーション
        current_pages = list_book_images(base_img_dir, book_name, path)
        _validate_permutation(request.page_indices, len(current_pages))

        new_total = reorder_book_image_pages(book_img_dir, request.page_indices)

        # 並び替え後の先頭 WebP から表紙再生成
        webps = list_book_images(base_img_dir, book_name, path)
        if webps:
            generate_thumbnail_from_image(webps[0], thumb_path)
            logger.info("Regenerated thumbnail: %s", thumb_path)

        return {"message": "Pages reordered successfully", "total_pages": new_total}

    # kindle / novel: PDF を fitz で再構築
    base_pdf_dir = dirs["pdf"]
    pdf_path = os.path.join(base_pdf_dir, path, filename) if path else os.path.join(base_pdf_dir, filename)

    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="File not found")

    with fitz.open(pdf_path) as doc:
        _validate_permutation(request.page_indices, len(doc))

    new_total = PdfService.reorder_pages(pdf_path, request.page_indices)

    ThumbnailService.generate_thumbnail(pdf_path, thumb_path)
    logger.info("Regenerated thumbnail: %s", thumb_path)

    return {"message": "Pages reordered successfully", "total_pages": new_total}


class MergePdfsRequest(BaseModel):
    names: list[str]   # 結合対象の .pdf ファイル名リスト（順序通りに結合）
    output_name: str   # 出力ファイル名（.pdf 拡張子付き）
    path: str = ""
    source: str = "generated"


@router.post("/pdfs/merge")
def merge_pdfs(request: MergePdfsRequest):
    """複数の PDF を順番に結合して新しい PDF を生成する。"""
    assert_valid_source(request.source)
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
