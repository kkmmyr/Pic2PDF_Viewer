from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
import os
from typing import Optional
import fitz
from config import get_dirs_by_source, SUPPORTED_IMAGE_FORMATS
from utils.path_utils import validate_safe_path, validate_safe_name, join_path
from utils.file_naming import get_thumbnail_name
from services.thumbnail_service import ThumbnailService
from services.file_manager import FileManager
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

@router.get("/pdfs")
def list_pdfs(background_tasks: BackgroundTasks, path: str = "", source: str = "generated"):
    validate_safe_path(path)

    dirs = get_dirs_by_source(source)
    base_pdf_dir = dirs["pdf"]
    base_thumb_dir = dirs["thumb"]
    url_prefix_thumb = dirs["thumb_url_prefix"]

    target_pdf_dir = join_path(base_pdf_dir, path)
    target_thumb_dir = join_path(base_thumb_dir, path)

    if not os.path.exists(target_pdf_dir):
        return {"files": [], "directories": [], "current_path": path}

    if not os.path.isdir(target_pdf_dir):
        raise HTTPException(status_code=400, detail="Not a directory")

    items = os.listdir(target_pdf_dir)
    files = []
    directories = []

    for item in items:
        item_path = join_path(target_pdf_dir, item)
        if os.path.isdir(item_path):
            directories.append(item)
        elif item.lower().endswith('.pdf'):
            thumb_name = get_thumbnail_name(item)
            thumb_path = join_path(target_thumb_dir, thumb_name)

            thumb_url = None
            if os.path.exists(thumb_path):
                rel_path = join_path(path, thumb_name) if path else thumb_name
                thumb_url = f"{url_prefix_thumb}/{rel_path}"
            else:
                background_tasks.add_task(ThumbnailService.generate_thumbnail, item_path, thumb_path)

            created_at = int(os.path.getctime(item_path))
            files.append({
                "name": item,
                "thumbnail": thumb_url,
                "created_at": created_at,
            })

    return {"files": files, "directories": directories, "current_path": path}

@router.get("/books/{path:path}/images")
def list_book_images(path: str, source: str = "generated"):
    validate_safe_path(path)

    dirs = get_dirs_by_source(source)
    base_images_dir = dirs["img"]
    url_prefix = dirs["thumb_url_prefix"].replace("/thumbnails", "/images")

    target_dir = join_path(base_images_dir, path)

    if not os.path.exists(target_dir):
        raise HTTPException(status_code=404, detail="Images not found")

    if not os.path.isdir(target_dir):
        raise HTTPException(status_code=400, detail="Not a directory")

    try:
        files = os.listdir(target_dir)
        images = [f for f in files if f.lower().endswith(SUPPORTED_IMAGE_FORMATS)]

        from natsort import natsorted
        images = natsorted(images)

        image_urls = []
        for img in images:
            rel_path = join_path(path, img)
            image_urls.append(f"{url_prefix}/{rel_path}")

        return {"images": image_urls}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class CreateDirectoryRequest(BaseModel):
    path: str
    name: str
    source: str = "generated"

@router.post("/directories")
def create_directory(request: CreateDirectoryRequest):
    validate_safe_path(request.path, param_name="path")
    validate_safe_name(request.name, param_name="name")

    dirs = get_dirs_by_source(request.source)
    base_pdf_dir = dirs["pdf"]

    target_dir = os.path.join(base_pdf_dir, request.path, request.name)

    if os.path.exists(target_dir):
        raise HTTPException(status_code=400, detail="Directory already exists")

    try:
        os.makedirs(target_dir)
        return {"message": "Directory created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class MoveItemsRequest(BaseModel):
    items: list[str]
    source_path: str
    destination_path: str
    source: str = "generated"

@router.post("/move")
def move_items(request: MoveItemsRequest):
    validate_safe_path(request.source_path, param_name="source_path")
    validate_safe_path(request.destination_path, param_name="destination_path")
    for item in request.items:
        validate_safe_name(item, param_name="item")

    dirs = get_dirs_by_source(request.source)

    moved_count = 0
    errors = []

    for item in request.items:
        try:
            FileManager.move_with_assets(item, request.source_path, request.destination_path, dirs)
            moved_count += 1
        except FileNotFoundError:
            errors.append(f"Item not found: {item}")
        except FileExistsError:
            errors.append(f"Destination exists: {item}")
        except OSError as e:
            errors.append(str(e))

    if moved_count == 0 and errors:
        raise HTTPException(status_code=500, detail="Failed to move items: " + "; ".join(errors))

    return {"message": "Items moved", "moved_count": moved_count, "errors": errors}


class RenameItemRequest(BaseModel):
    path: str
    old_name: str
    new_name: str
    source: str = "generated"
    is_folder: bool = False


@router.patch("/rename")
def rename_item(request: RenameItemRequest):
    validate_safe_path(request.path, param_name="path")
    validate_safe_name(request.old_name, param_name="old_name")
    validate_safe_name(request.new_name, param_name="new_name")

    dirs = get_dirs_by_source(request.source)

    try:
        FileManager.rename_with_assets(
            request.path, request.old_name, request.new_name, request.is_folder, dirs
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Item not found")
    except FileExistsError:
        raise HTTPException(status_code=400, detail="Name already exists")
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"message": "Item renamed", "new_name": request.new_name}


class RegenerateThumbnailRequest(BaseModel):
    path: str
    name: str  # .pdf 拡張子付きファイル名
    source: str = "generated"


@router.post("/thumbnails/regenerate")
def regenerate_thumbnail(request: RegenerateThumbnailRequest):
    validate_safe_path(request.path, param_name="path")
    validate_safe_name(request.name, param_name="name")

    dirs = get_dirs_by_source(request.source)

    pdf_path = os.path.join(dirs["pdf"], request.path, request.name)
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF not found")

    thumb_name = get_thumbnail_name(request.name)
    thumb_path = os.path.join(dirs["thumb"], request.path, thumb_name)

    ok = ThumbnailService.generate_thumbnail(pdf_path, thumb_path)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to regenerate thumbnail")

    return {"message": "Thumbnail regenerated"}


class RegenerateThumbnailBulkRequest(BaseModel):
    names: list[str]  # .pdf 拡張子付きファイル名のリスト
    path: str = ""
    source: str = "generated"


@router.post("/thumbnails/regenerate_bulk")
def regenerate_thumbnail_bulk(request: RegenerateThumbnailBulkRequest):
    """複数書籍のサムネイルを一括再生成する。"""
    validate_safe_path(request.path, param_name="path")
    for name in request.names:
        validate_safe_name(name, param_name="name")

    dirs = get_dirs_by_source(request.source)
    succeeded = []
    failed = []

    for name in request.names:
        pdf_path = os.path.join(dirs["pdf"], request.path, name)
        if not os.path.exists(pdf_path):
            failed.append(name)
            continue
        thumb_name = get_thumbnail_name(name)
        thumb_path = os.path.join(dirs["thumb"], request.path, thumb_name)
        ok = ThumbnailService.generate_thumbnail(pdf_path, thumb_path)
        if ok:
            succeeded.append(name)
            logger.info("Regenerated thumbnail: %s", thumb_path)
        else:
            failed.append(name)
            logger.warning("Failed to regenerate thumbnail: %s", thumb_path)

    return {"message": "Bulk thumbnail regeneration complete", "succeeded": succeeded, "failed": failed}


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

    if not request.output_name.lower().endswith(".pdf"):
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
