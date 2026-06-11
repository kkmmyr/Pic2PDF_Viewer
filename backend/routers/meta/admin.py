"""メタデータ管理者向け一括操作エンドポイント。"""

import os

from fastapi import APIRouter, Depends

from config import get_dirs_by_source
from routers._deps import validated_source
from routers.api_schemas import AdminInitResponse
from services.meta_store import update_meta_locked
from utils.file_utils import is_image_file

router = APIRouter()


@router.post("/meta/init-genre-original", response_model=AdminInitResponse)
def init_genre_original(source: str = Depends(validated_source)) -> dict:
    """genre 未設定の書籍に genre=オリジナル を一括設定する。

    - meta.db にエントリがあるが genre が空のもの → オリジナルに更新
    - images/ ディレクトリにあるが meta.db に未登録のもの → エントリを新規追加
    """
    dirs = get_dirs_by_source(source)
    img_root = dirs["img"]

    # images/ 配下の書籍ディレクトリを再帰収集
    fs_book_ids: set[str] = set()
    _collect_book_ids(img_root, "", fs_book_ids)

    updated = 0
    inserted = 0

    def _apply(data: dict) -> None:
        nonlocal updated, inserted
        for entry in data.values():
            if not entry.get("genre"):
                entry["genre"] = "オリジナル"
                updated += 1
        for book_id in fs_book_ids:
            if book_id not in data:
                data[book_id] = {"authors": [], "genre": "オリジナル"}
                inserted += 1

    update_meta_locked(source, _apply)
    return {"updated": updated, "inserted": inserted}


def _collect_book_ids(img_root: str, rel_path: str, result: set[str]) -> None:
    """images/ を再帰走査し、画像を直接含むディレクトリの book_id を収集する。"""
    target = os.path.join(img_root, rel_path) if rel_path else img_root
    if not os.path.isdir(target):
        return
    for item in os.listdir(target):
        item_abs = os.path.join(target, item)
        if not os.path.isdir(item_abs):
            continue
        has_images = any(is_image_file(f) for f in os.listdir(item_abs))
        if has_images:
            book_id = f"{rel_path}/{item}.pdf" if rel_path else f"{item}.pdf"
            result.add(book_id)
        else:
            next_rel = f"{rel_path}/{item}" if rel_path else item
            _collect_book_ids(img_root, next_rel, result)
