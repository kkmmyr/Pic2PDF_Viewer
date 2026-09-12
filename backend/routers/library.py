import os
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from config import get_dirs_by_source
from routers._deps import assert_valid_source, log_and_raise_500, validate_request_targets, validated_source
from routers.api_schemas import BookImagesResponse, DeleteResponse, PdfListResponse, RenameResponse
from services.file_manager import FileManager
from services.library.image_listing import (
    ImageDirectoryMissingError,
    ImageDirectoryNotDirectoryError,
    list_book_image_files,
)
from services.library_listing import invalidate_library_listing, list_library_books
from services.meta_store import make_key, update_meta_locked
from utils.logger import get_logger
from utils.path_utils import join_path, resolve_under_base, validate_safe_name, validate_safe_path

logger = get_logger(__name__)

router = APIRouter()


@router.get("/pdfs", response_model=PdfListResponse)
def list_pdfs(background_tasks: BackgroundTasks, path: str = "", source: str = Depends(validated_source)):
    validate_safe_path(path)

    dirs = get_dirs_by_source(source)
    from services.pdf_generator import generate_thumbnail as generate_thumbnail_from_image

    def schedule_thumbnail(image_path: str, thumbnail_path: str) -> None:
        background_tasks.add_task(generate_thumbnail_from_image, image_path, thumbnail_path)
        background_tasks.add_task(invalidate_library_listing, source, path)

    try:
        return list_library_books(source, path, dirs, schedule_thumbnail)
    except NotADirectoryError as error:
        raise HTTPException(status_code=400, detail="Not a directory") from error


@router.get("/books/{path:path}/images", response_model=BookImagesResponse)
@log_and_raise_500("list_book_images")
def list_book_images(path: str, source: str = Depends(validated_source)) -> dict[str, list[str]]:
    validate_safe_path(path)

    dirs = get_dirs_by_source(source)
    base_images_dir = dirs["img"]
    url_prefix = dirs["thumb_url_prefix"].replace("/thumbnails", "/images")

    target_dir = resolve_under_base(base_images_dir, path)

    try:
        images = list_book_image_files(target_dir)
    except ImageDirectoryMissingError as error:
        raise HTTPException(status_code=404, detail="Images not found") from error
    except ImageDirectoryNotDirectoryError as error:
        raise HTTPException(status_code=400, detail="Not a directory") from error

    image_urls = []
    for img in images:
        rel_path = join_path(path, img.name)
        encoded = "/".join(quote(seg, safe="") for seg in rel_path.replace(os.sep, "/").split("/"))
        image_urls.append(f"{url_prefix}/{encoded}?v={img.mtime_ns}")

    return {"images": image_urls}


class RenameItemRequest(BaseModel):
    path: str
    old_name: str
    new_name: str
    source: str = "doujin"
    is_folder: bool = False


@router.patch("/rename", response_model=RenameResponse)
def rename_item(request: RenameItemRequest):
    assert_valid_source(request.source)
    validate_safe_path(request.path, param_name="path")
    validate_safe_name(request.old_name, param_name="old_name")
    validate_safe_name(request.new_name, param_name="new_name")

    dirs = get_dirs_by_source(request.source)

    try:
        FileManager.rename_with_assets(request.path, request.old_name, request.new_name, request.is_folder, dirs)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="Item not found") from e
    except FileExistsError as e:
        raise HTTPException(status_code=400, detail="Name already exists") from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    # meta.json のキーを旧名→新名に付け替える（作者名・タグ・シリーズを引き継ぐ）
    old_key = make_key(request.path, request.old_name)
    new_key = make_key(request.path, request.new_name)

    def _rename_meta_key(data):
        if request.is_folder:
            old_prefix = old_key + "/"
            new_prefix = new_key + "/"
            for k in list(data.keys()):
                if k.startswith(old_prefix):
                    data[new_prefix + k[len(old_prefix) :]] = data.pop(k)
        else:
            if old_key in data:
                data[new_key] = data.pop(old_key)

    update_meta_locked(request.source, _rename_meta_key)
    invalidate_library_listing(request.source, request.path)

    return {"message": "Item renamed", "new_name": request.new_name}


class DeletePdfsRequest(BaseModel):
    names: list[str]
    path: str = ""
    source: str = "doujin"


@router.delete("/pdfs", response_model=DeleteResponse)
def delete_pdfs(request: DeletePdfsRequest):
    assert_valid_source(request.source)
    validate_request_targets(request.path, request.names)

    dirs = get_dirs_by_source(request.source)
    deleted_count = 0
    errors = []

    deleted_keys: list[str] = []
    for name in request.names:
        try:
            FileManager.delete_with_assets(name, request.path, dirs)
            deleted_keys.append(make_key(request.path, name))
            deleted_count += 1
        except FileNotFoundError:
            errors.append(f"Not found: {name}")
        except OSError as e:
            errors.append(str(e))

    if deleted_count == 0 and errors:
        raise HTTPException(status_code=500, detail="削除に失敗しました: " + "; ".join(errors))

    if deleted_keys:

        def _drop_deleted(data: dict) -> None:
            for key in deleted_keys:
                data.pop(key, None)

        update_meta_locked(request.source, _drop_deleted)
        invalidate_library_listing(request.source, request.path)

    return {"message": "Items deleted", "deleted_count": deleted_count, "errors": errors}
