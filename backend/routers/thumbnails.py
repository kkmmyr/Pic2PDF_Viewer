"""
サムネイル管理ルーター。
PDF サムネイルの単発再生成・一括再生成、および任意ページのオンデマンド生成を提供する。
"""
import os

import fitz
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from config import get_dirs_by_source
from routers._deps import assert_valid_source, validate_request_targets, validated_source
from services.image_service import list_book_images
from services.pdf_generator import generate_thumbnail as generate_thumbnail_from_image
from services.thumbnail_service import ThumbnailService
from utils.file_naming import get_thumbnail_name
from utils.logger import get_logger
from utils.path_utils import validate_safe_name, validate_safe_path

logger = get_logger(__name__)

router = APIRouter()


class RegenerateThumbnailRequest(BaseModel):
    path: str
    name: str  # .pdf 拡張子付きファイル名
    source: str = "doujin"


class RegenerateThumbnailBulkRequest(BaseModel):
    names: list[str]  # .pdf 拡張子付きファイル名のリスト
    path: str = ""
    source: str = "doujin"


def _regenerate_one(pdf_dir: str, thumb_dir: str, path: str, name: str, img_dir: str = "") -> bool:
    """1冊分のサムネイル再生成。成功時 True を返す。

    PDF が存在しない場合（generated image-only モード）は
    img_dir 配下の先頭 WebP を `pdf_generator.generate_thumbnail`（PIL ベース）で処理する。
    fitz は WebP を読めないため、画像→JPG は PIL 経路を使う必要がある。
    """
    thumb_name = get_thumbnail_name(name)
    thumb_path = os.path.join(thumb_dir, path, thumb_name) if path else os.path.join(thumb_dir, thumb_name)

    pdf_path = os.path.join(pdf_dir, path, name) if path else os.path.join(pdf_dir, name)
    if os.path.exists(pdf_path):
        return ThumbnailService.generate_thumbnail(pdf_path, thumb_path)

    # PDF 不在: images/ 先頭 WebP を PIL ベースで処理（image-only モード）
    if img_dir:
        webps = list_book_images(img_dir, os.path.splitext(name)[0], path)
        if webps:
            return generate_thumbnail_from_image(webps[0], thumb_path)

    return False


@router.get("/thumbnails/page")
def get_page_thumbnail(
    name: str = Query(...),
    page: int = Query(...),
    path: str = Query(""),
    source: str = Depends(validated_source),
    width: int = Query(120),
):
    """指定ページのサムネイル画像をオンデマンド生成して返す。ページスライダーのプレビュー用。

    generated ソースは images/ 配下の WebP を直接返す。
    kindle / novel は PDF を fitz でレンダリングして返す。
    """
    validate_safe_path(path, param_name="path")
    validate_safe_name(name, param_name="name")
    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")

    dirs = get_dirs_by_source(source)

    # generated: images/ ディレクトリから該当ページの WebP を直接返す
    if source == "doujin":
        book_name = os.path.splitext(name)[0]
        webps = list_book_images(dirs["img"], book_name, path)
        if not webps:
            raise HTTPException(status_code=404, detail="Images not found")
        if page > len(webps):
            raise HTTPException(status_code=400, detail="page out of range")
        with open(webps[page - 1], "rb") as f:
            img_bytes = f.read()
        return Response(
            content=img_bytes,
            media_type="image/webp",
            headers={"Cache-Control": "max-age=3600"},
        )

    # kindle / novel: PDF を fitz でレンダリング
    pdf_path = os.path.join(dirs["pdf"], path, name) if path else os.path.join(dirs["pdf"], name)
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF not found")

    try:
        with fitz.open(pdf_path) as doc:
            if page > len(doc):
                raise HTTPException(status_code=400, detail="page out of range")
            pg = doc.load_page(page - 1)
            scale = width / pg.rect.width
            pix = pg.get_pixmap(matrix=fitz.Matrix(scale, scale))
            img_bytes = pix.tobytes("jpeg")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to render page thumbnail for %s page %d: %s", name, page, e)
        raise HTTPException(status_code=500, detail="Failed to render thumbnail") from e

    return Response(
        content=img_bytes,
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=3600"},
    )


@router.post("/thumbnails/regenerate")
def regenerate_thumbnail(request: RegenerateThumbnailRequest):
    assert_valid_source(request.source)
    validate_safe_path(request.path, param_name="path")
    validate_safe_name(request.name, param_name="name")

    dirs = get_dirs_by_source(request.source)
    if not _regenerate_one(dirs["pdf"], dirs["thumb"], request.path, request.name, dirs["img"]):
        raise HTTPException(status_code=404, detail="Source image not found")

    return {"message": "Thumbnail regenerated"}


@router.post("/thumbnails/regenerate_bulk")
def regenerate_thumbnail_bulk(request: RegenerateThumbnailBulkRequest):
    """複数書籍のサムネイルを一括再生成する。"""
    assert_valid_source(request.source)
    validate_request_targets(request.path, request.names)

    dirs = get_dirs_by_source(request.source)
    succeeded: list[str] = []
    failed: list[str] = []

    for name in request.names:
        if _regenerate_one(dirs["pdf"], dirs["thumb"], request.path, name, dirs["img"]):
            succeeded.append(name)
            logger.info("Regenerated thumbnail: %s", name)
        else:
            failed.append(name)
            logger.warning("Failed to regenerate thumbnail: %s", name)

    return {"message": "Bulk thumbnail regeneration complete", "succeeded": succeeded, "failed": failed}
