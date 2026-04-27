"""
サムネイル管理ルーター。
PDF サムネイルの単発再生成・一括再生成を提供する。
"""
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import get_dirs_by_source
from services.thumbnail_service import ThumbnailService
from utils.path_utils import validate_safe_path, validate_safe_name
from utils.file_naming import get_thumbnail_name
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


class RegenerateThumbnailRequest(BaseModel):
    path: str
    name: str  # .pdf 拡張子付きファイル名
    source: str = "generated"


class RegenerateThumbnailBulkRequest(BaseModel):
    names: list[str]  # .pdf 拡張子付きファイル名のリスト
    path: str = ""
    source: str = "generated"


def _regenerate_one(pdf_dir: str, thumb_dir: str, path: str, name: str) -> bool:
    """1冊分のサムネイル再生成。成功時 True を返す。"""
    pdf_path = os.path.join(pdf_dir, path, name)
    if not os.path.exists(pdf_path):
        return False
    thumb_name = get_thumbnail_name(name)
    thumb_path = os.path.join(thumb_dir, path, thumb_name)
    return ThumbnailService.generate_thumbnail(pdf_path, thumb_path)


@router.post("/thumbnails/regenerate")
def regenerate_thumbnail(request: RegenerateThumbnailRequest):
    validate_safe_path(request.path, param_name="path")
    validate_safe_name(request.name, param_name="name")

    dirs = get_dirs_by_source(request.source)
    pdf_path = os.path.join(dirs["pdf"], request.path, request.name)
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF not found")

    if not _regenerate_one(dirs["pdf"], dirs["thumb"], request.path, request.name):
        raise HTTPException(status_code=500, detail="Failed to regenerate thumbnail")

    return {"message": "Thumbnail regenerated"}


@router.post("/thumbnails/regenerate_bulk")
def regenerate_thumbnail_bulk(request: RegenerateThumbnailBulkRequest):
    """複数書籍のサムネイルを一括再生成する。"""
    validate_safe_path(request.path, param_name="path")
    for name in request.names:
        validate_safe_name(name, param_name="name")

    dirs = get_dirs_by_source(request.source)
    succeeded: list[str] = []
    failed: list[str] = []

    for name in request.names:
        if _regenerate_one(dirs["pdf"], dirs["thumb"], request.path, name):
            succeeded.append(name)
            logger.info("Regenerated thumbnail: %s", name)
        else:
            failed.append(name)
            logger.warning("Failed to regenerate thumbnail: %s", name)

    return {"message": "Bulk thumbnail regeneration complete", "succeeded": succeeded, "failed": failed}
