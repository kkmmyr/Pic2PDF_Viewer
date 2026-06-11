import os
from collections.abc import Callable
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from natsort import natsorted
from pydantic import BaseModel

from config import SourceDirs, get_dirs_by_source
from routers._deps import assert_valid_source, log_and_raise_500, validate_request_targets, validated_source
from services.file_manager import FileManager
from services.meta_store import MetaDict, make_key, update_meta_locked
from services.pdf_generator import generate_thumbnail as generate_thumbnail_from_image
from utils.file_naming import get_thumbnail_name
from utils.file_utils import is_image_file
from utils.logger import get_logger
from utils.path_utils import join_path, validate_safe_name, validate_safe_path

logger = get_logger(__name__)

router = APIRouter()


def _list_from_images(background_tasks: BackgroundTasks, path: str, dirs: SourceDirs) -> dict:
    """images/ サブディレクトリを走査して書籍一覧を返す（全ソース共通）。

    images/{book}/ ディレクトリを正とし、WebP / PNG / JPG 等任意の画像形式に対応。
    返却する name は "{dirname}.pdf" として meta.db のキー互換を保つ。
    """
    base_img_dir = dirs["img"]
    base_thumb_dir = dirs["thumb"]
    url_prefix_thumb = dirs["thumb_url_prefix"]

    target_img_dir = join_path(base_img_dir, path) if path else base_img_dir
    target_thumb_dir = join_path(base_thumb_dir, path) if path else base_thumb_dir

    if not os.path.exists(target_img_dir):
        return {"files": [], "current_path": path}

    if not os.path.isdir(target_img_dir):
        raise HTTPException(status_code=400, detail="Not a directory")

    files = []
    for item in os.listdir(target_img_dir):
        item_path = join_path(target_img_dir, item)
        if not os.path.isdir(item_path):
            continue
        imgs = natsorted([f for f in os.listdir(item_path) if is_image_file(f)])
        if not imgs:
            continue

        pdf_name = f"{item}.pdf"
        thumb_name = get_thumbnail_name(pdf_name)
        thumb_path = join_path(target_thumb_dir, thumb_name)

        thumb_url = None
        if os.path.exists(thumb_path):
            rel = join_path(path, thumb_name) if path else thumb_name
            encoded = "/".join(quote(seg, safe="") for seg in rel.replace(os.sep, "/").split("/"))
            thumb_url = f"{url_prefix_thumb}/{encoded}"
        else:
            # fitz は WebP を読めないため PIL 経路で生成（PNG/JPG も同様に対応）
            first_img = join_path(item_path, imgs[0])
            background_tasks.add_task(generate_thumbnail_from_image, first_img, thumb_path)

        created_at = int(os.path.getctime(item_path))
        files.append(
            {
                "name": pdf_name,
                "thumbnail": thumb_url,
                "created_at": created_at,
            }
        )

    return {"files": files, "current_path": path}


@router.get("/pdfs")
def list_pdfs(background_tasks: BackgroundTasks, path: str = "", source: str = Depends(validated_source)):
    validate_safe_path(path)

    dirs = get_dirs_by_source(source)

    # 全ソース共通: images/ サブディレクトリを走査（WebP / PNG / JPG を含むフォルダを書籍として返す）
    return _list_from_images(background_tasks, path, dirs)


@router.get("/books/{path:path}/images")
@log_and_raise_500("list_book_images")
def list_book_images(path: str, source: str = Depends(validated_source)):
    validate_safe_path(path)

    dirs = get_dirs_by_source(source)
    base_images_dir = dirs["img"]
    url_prefix = dirs["thumb_url_prefix"].replace("/thumbnails", "/images")

    target_dir = join_path(base_images_dir, path)

    if not os.path.exists(target_dir):
        raise HTTPException(status_code=404, detail="Images not found")

    if not os.path.isdir(target_dir):
        raise HTTPException(status_code=400, detail="Not a directory")

    files = os.listdir(target_dir)
    images = [f for f in files if is_image_file(f)]

    from natsort import natsorted

    images = natsorted(images)

    image_urls = []
    for img in images:
        rel_path = join_path(path, img)
        encoded = "/".join(quote(seg, safe="") for seg in rel_path.replace(os.sep, "/").split("/"))
        image_urls.append(f"{url_prefix}/{encoded}")

    return {"images": image_urls}


class RenameItemRequest(BaseModel):
    path: str
    old_name: str
    new_name: str
    source: str = "doujin"
    is_folder: bool = False


@router.patch("/rename")
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

    return {"message": "Item renamed", "new_name": request.new_name}


class DeletePdfsRequest(BaseModel):
    names: list[str]
    path: str = ""
    source: str = "doujin"


@router.delete("/pdfs")
def delete_pdfs(request: DeletePdfsRequest):
    assert_valid_source(request.source)
    validate_request_targets(request.path, request.names)

    dirs = get_dirs_by_source(request.source)
    deleted_count = 0
    errors = []

    def _make_dropper(k: str) -> Callable[[MetaDict], None]:
        def _drop(data: MetaDict) -> None:
            data.pop(k, None)

        return _drop

    for name in request.names:
        try:
            FileManager.delete_with_assets(name, request.path, dirs)
            key = make_key(request.path, name)
            update_meta_locked(request.source, _make_dropper(key))
            deleted_count += 1
        except FileNotFoundError:
            errors.append(f"Not found: {name}")
        except OSError as e:
            errors.append(str(e))

    if deleted_count == 0 and errors:
        raise HTTPException(status_code=500, detail="削除に失敗しました: " + "; ".join(errors))

    return {"message": "Items deleted", "deleted_count": deleted_count, "errors": errors}
