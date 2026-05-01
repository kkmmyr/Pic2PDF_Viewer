from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
import os
from urllib.parse import quote

from config import get_dirs_by_source
from utils.file_utils import is_image_file, is_pdf_file
from utils.path_utils import validate_safe_path, validate_safe_name, join_path
from utils.file_naming import get_thumbnail_name
from services.thumbnail_service import ThumbnailService
from services.file_manager import FileManager
from services.meta_store import make_key, update_meta_locked
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
        return {"files": [], "current_path": path}

    if not os.path.isdir(target_pdf_dir):
        raise HTTPException(status_code=400, detail="Not a directory")

    items = os.listdir(target_pdf_dir)
    files = []

    for item in items:
        item_path = join_path(target_pdf_dir, item)
        if os.path.isdir(item_path):
            continue
        elif is_pdf_file(item):
            thumb_name = get_thumbnail_name(item)
            thumb_path = join_path(target_thumb_dir, thumb_name)

            thumb_url = None
            if os.path.exists(thumb_path):
                rel_path = join_path(path, thumb_name) if path else thumb_name
                encoded = '/'.join(quote(seg, safe='') for seg in rel_path.replace(os.sep, '/').split('/'))
                thumb_url = f"{url_prefix_thumb}/{encoded}"
            else:
                background_tasks.add_task(ThumbnailService.generate_thumbnail, item_path, thumb_path)

            created_at = int(os.path.getctime(item_path))
            files.append({
                "name": item,
                "thumbnail": thumb_url,
                "created_at": created_at,
            })

    return {"files": files, "current_path": path}

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
        images = [f for f in files if is_image_file(f)]

        from natsort import natsorted
        images = natsorted(images)

        image_urls = []
        for img in images:
            rel_path = join_path(path, img)
            encoded = '/'.join(quote(seg, safe='') for seg in rel_path.replace(os.sep, '/').split('/'))
            image_urls.append(f"{url_prefix}/{encoded}")

        return {"images": image_urls}
    except Exception as e:
        logger.exception("list_book_images failed: %s", path)
        raise HTTPException(status_code=500, detail=str(e))

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

    # meta.json のキーを旧名→新名に付け替える（作者名・タグ・シリーズを引き継ぐ）
    old_key = make_key(request.path, request.old_name)
    new_key = make_key(request.path, request.new_name)

    def _rename_meta_key(data):
        if request.is_folder:
            old_prefix = old_key + "/"
            new_prefix = new_key + "/"
            for k in list(data.keys()):
                if k.startswith(old_prefix):
                    data[new_prefix + k[len(old_prefix):]] = data.pop(k)
        else:
            if old_key in data:
                data[new_key] = data.pop(old_key)

    update_meta_locked(request.source, _rename_meta_key)

    return {"message": "Item renamed", "new_name": request.new_name}


class DeletePdfsRequest(BaseModel):
    names: list[str]
    path: str = ""
    source: str = "generated"


@router.delete("/pdfs")
def delete_pdfs(request: DeletePdfsRequest):
    validate_safe_path(request.path, param_name="path")
    for name in request.names:
        validate_safe_name(name, param_name="name")

    dirs = get_dirs_by_source(request.source)
    deleted_count = 0
    errors = []

    for name in request.names:
        try:
            FileManager.delete_with_assets(name, request.path, dirs)
            key = make_key(request.path, name)
            update_meta_locked(request.source, lambda data, k=key: data.pop(k, None))
            deleted_count += 1
        except FileNotFoundError:
            errors.append(f"Not found: {name}")
        except OSError as e:
            errors.append(str(e))

    if deleted_count == 0 and errors:
        raise HTTPException(status_code=500, detail="削除に失敗しました: " + "; ".join(errors))

    return {"message": "Items deleted", "deleted_count": deleted_count, "errors": errors}
