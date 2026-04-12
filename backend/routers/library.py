from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
import os
import shutil
import fitz
from typing import Optional, List
from config import get_dirs_by_source
from utils.path_utils import validate_safe_path, validate_safe_name, join_path

router = APIRouter()

from services.thumbnail_service import ThumbnailService

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
            thumb_name = os.path.splitext(item)[0] + ".jpg"
            thumb_path = join_path(target_thumb_dir, thumb_name)

            thumb_url = None
            if os.path.exists(thumb_path):
                rel_path = join_path(path, thumb_name) if path else thumb_name
                thumb_url = f"{url_prefix_thumb}/{rel_path}"
            else:
                background_tasks.add_task(ThumbnailService.generate_thumbnail, item_path, thumb_path)

            files.append({
                "name": item,
                "thumbnail": thumb_url
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
        images = [f for f in files if f.lower().endswith(('.webp', '.jpg', '.jpeg', '.png'))]

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
        moved_parts: list[tuple[str, str]] = []  # (移動先, 移動元) — ロールバック用
        try:
            src_pdf = os.path.join(dirs["pdf"], request.source_path, item)
            dst_pdf = os.path.join(dirs["pdf"], request.destination_path, item)

            if not os.path.exists(src_pdf):
                errors.append(f"Item not found: {item}")
                continue

            if os.path.exists(dst_pdf):
                errors.append(f"Destination exists: {item}")
                continue

            # PDF を移動
            os.makedirs(os.path.dirname(dst_pdf), exist_ok=True)
            shutil.move(src_pdf, dst_pdf)
            moved_parts.append((dst_pdf, src_pdf))

            # サムネイルを移動
            if os.path.isdir(dst_pdf):
                src_thumb = os.path.join(dirs["thumb"], request.source_path, item)
                dst_thumb = os.path.join(dirs["thumb"], request.destination_path, item)
            else:
                thumb_name = os.path.splitext(item)[0] + ".jpg"
                src_thumb = os.path.join(dirs["thumb"], request.source_path, thumb_name)
                dst_thumb = os.path.join(dirs["thumb"], request.destination_path, thumb_name)

            if os.path.exists(src_thumb):
                os.makedirs(os.path.dirname(dst_thumb), exist_ok=True)
                shutil.move(src_thumb, dst_thumb)
                moved_parts.append((dst_thumb, src_thumb))

            # 画像ディレクトリを移動
            book_name = os.path.splitext(item)[0] if item.lower().endswith('.pdf') else item
            src_img = os.path.join(dirs["img"], request.source_path, book_name)
            dst_img = os.path.join(dirs["img"], request.destination_path, book_name)

            if os.path.exists(src_img):
                os.makedirs(os.path.dirname(dst_img), exist_ok=True)
                shutil.move(src_img, dst_img)
                moved_parts.append((dst_img, src_img))

            moved_count += 1

        except Exception as e:
            # 移動済みファイルを元の場所に戻す
            for moved_dst, original_src in reversed(moved_parts):
                try:
                    shutil.move(moved_dst, original_src)
                except Exception as rollback_err:
                    errors.append(f"Rollback failed for {moved_dst}: {str(rollback_err)}")
            errors.append(f"Error moving {item}: {str(e)}")

    if moved_count == 0 and errors:
        raise HTTPException(status_code=500, detail="Failed to move items: " + "; ".join(errors))

    return {"message": "Items moved", "moved_count": moved_count, "errors": errors}
