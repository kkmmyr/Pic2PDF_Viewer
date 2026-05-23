"""
書籍メタデータ管理ルーター。

各ソースの meta.json に作者名などを保存・取得する。
保存先: backend/data/meta/{source}/meta.json
キー: "{path}/{filename}" の相対パス（path が空の場合は "{filename}"）
"""
import json
import os
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from config import get_dirs_by_source
from routers._deps import assert_valid_source, validate_request_targets, validated_source
from services.meta_store import (
    VALID_READ_STATES,
    has_meaningful_value,
    load_meta,
    make_key,
    merge_entry_fields,
    update_meta_locked,
)
from utils.dt import JST
from utils.file_utils import is_image_file
from utils.path_utils import validate_safe_name, validate_safe_path

router = APIRouter()

# 同じ書籍を短時間に何度開いても view_count を膨らませない閾値（秒）
VIEW_COUNT_DEBOUNCE_SEC = 300


# ---------------------------------------------------------------------------
# リクエスト/レスポンスモデル
# ---------------------------------------------------------------------------

class UpdateMetaRequest(BaseModel):
    """単一書籍または複数書籍へのメタデータ更新リクエスト。

    `authors` / `hidden` / `genre` / `read_state` は省略可。省略されたフィールドは変更しない。
    すべて省略するとエラー（更新する内容が無い）。
    """
    path: str = ""
    names: list[str]
    authors: list[str] | None = None
    hidden: bool | None = None
    genre: str | None = None
    read_state: str | None = None
    source: str = "doujin"


class RecordViewRequest(BaseModel):
    """閲覧記録リクエスト。"""
    path: str = ""
    name: str
    source: str = "doujin"


# ---------------------------------------------------------------------------
# エンドポイント
# ---------------------------------------------------------------------------

@router.get("/meta")
def get_meta(source: str = Depends(validated_source)) -> dict:
    """
    指定ソースの meta.json 全体を返す。
    レスポンス: { "key": { "authors": [...] }, ... }
    """
    return load_meta(source)


@router.get("/meta/export")
def export_meta(source: str = Depends(validated_source)) -> Response:
    """
    指定ソースの meta.json 全体を JSON ファイルとしてダウンロードする。
    バックアップ・環境移行用。副作用なし（読み取り専用）。
    """
    data = load_meta(source)
    json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    date_str = datetime.now(JST).strftime("%Y%m%d")
    filename = f"meta_{source}_{date_str}.json"
    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/meta")
def update_meta(request: UpdateMetaRequest) -> dict:
    """1冊または複数冊のメタデータ（作者名 / 非表示フラグ / ジャンル / 読書状態）を上書き保存する。

    指定したフィールドのみ書き換え、省略されたフィールドは保持する。
    すべての list フィールドが空になった場合はエントリ自体を削除する。
    """
    assert_valid_source(request.source)
    if (
        request.authors is None
        and request.hidden is None
        and request.genre is None
        and request.read_state is None
    ):
        raise HTTPException(
            status_code=400,
            detail="authors, hidden, genre, or read_state must be specified",
        )
    if (
        request.read_state is not None
        and request.read_state != ""
        and request.read_state not in VALID_READ_STATES
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid read_state. Choose from: {', '.join(VALID_READ_STATES)} or '' to clear",
        )

    validate_request_targets(request.path, request.names)

    # 各フィールドを正規化（None ならそのまま）
    authors = [a.strip() for a in request.authors if a.strip()] if request.authors is not None else None
    genre = request.genre.strip() if request.genre is not None else None

    def _apply(data):
        for name in request.names:
            key = make_key(request.path, name)
            merged = merge_entry_fields(
                data.get(key, {}),
                authors=authors,
                hidden=request.hidden,
                genre=genre,
                read_state=request.read_state,
            )
            # 非 list フィールド（view_count / hidden 等）が残っていればエントリは保持
            if has_meaningful_value(merged):
                data[key] = merged
            else:
                data.pop(key, None)

    update_meta_locked(request.source, _apply)
    return {"message": "Updated", "updated_count": len(request.names)}


class NovelMetaPatchRequest(BaseModel):
    """novel 1 冊のメタを部分更新するリクエスト（4.3）。省略されたフィールドは変更しない。"""
    authors: list[str] | None = None
    series_id: str | None = None
    volume: int | None = None
    volume_clear: bool = False
    publisher: str | None = None
    asin: str | None = None
    isbn: str | None = None
    release_date: str | None = None


@router.patch("/meta/novel/{book_key:path}")
def patch_novel_meta(book_key: str, request: NovelMetaPatchRequest) -> dict:
    """novel ソースの 1 冊メタを部分更新する（4.3）。

    book_key は "{stem}.pdf" 形式。省略フィールドは変更しない。
    """
    all_none = (
        request.authors is None
        and request.series_id is None
        and not request.volume_clear
        and request.volume is None
        and request.publisher is None
        and request.asin is None
        and request.isbn is None
        and request.release_date is None
    )
    if all_none:
        raise HTTPException(status_code=400, detail="No fields to update")

    def _apply(data: dict) -> None:
        entry = dict(data.get(book_key, {}))
        if request.authors is not None:
            cleaned = [a.strip() for a in request.authors if a.strip()]
            entry["authors"] = cleaned
        if request.series_id is not None:
            if request.series_id:
                entry["series_id"] = request.series_id
                entry["series_title"] = request.series_id
            else:
                entry.pop("series_id", None)
                entry.pop("series_title", None)
        if request.volume_clear:
            entry.pop("volume", None)
        elif request.volume is not None:
            entry["volume"] = request.volume
        for field in ("publisher", "asin", "isbn", "release_date"):
            val = getattr(request, field)
            if val is not None:
                if val:
                    entry[field] = val
                else:
                    entry.pop(field, None)
        data[book_key] = entry

    update_meta_locked("novel", _apply)
    return {"message": "Updated"}


@router.post("/meta/init-genre-original")
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


@router.post("/meta/view")
def record_view(request: RecordViewRequest) -> dict:
    """書籍の閲覧を記録する。

    - `last_viewed_at` は呼び出し毎に常に現在時刻で更新（最近見た順ソート用）。
    - `view_count` は前回 last_viewed_at から VIEW_COUNT_DEBOUNCE_SEC 以上経過した場合のみ +1。
      短時間で同じ書籍を何度も開いてもカウントが膨らまないようにする。
    """
    assert_valid_source(request.source)

    validate_safe_path(request.path, param_name="path")
    validate_safe_name(request.name, param_name="name")

    key = make_key(request.path, request.name)
    now = time.time()
    result = {}

    def _apply(data):
        existing = data.get(key, {})
        prev_count = int(existing.get("view_count", 0))
        prev_viewed_at = existing.get("last_viewed_at")
        should_increment = (
            prev_viewed_at is None
            or (now - float(prev_viewed_at)) >= VIEW_COUNT_DEBOUNCE_SEC
        )
        new_count = prev_count + 1 if should_increment else prev_count
        merged = {**existing, "view_count": new_count, "last_viewed_at": now}
        # 読書状態の自動遷移: カウント増加時のみ unread/未設定 → reading に書き換える。
        # done は維持（読了済みの再読でも done を保つ）。連打抑制で据え置き時は変更しない。
        if should_increment and existing.get("read_state") != "done":
            merged["read_state"] = "reading"
        data[key] = merged
        result["view_count"] = new_count
        result["last_viewed_at"] = now
        result["incremented"] = should_increment
        result["read_state"] = merged.get("read_state")

    update_meta_locked(request.source, _apply)
    return result
