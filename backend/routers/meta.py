"""
書籍メタデータ管理ルーター。

各ソースの meta.json に作者名などを保存・取得する。
保存先: backend/data/meta/{source}/meta.json
キー: "{path}/{filename}" の相対パス（path が空の場合は "{filename}"）
"""
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from config import get_dirs_by_source
from utils.path_utils import validate_safe_path, validate_safe_name
from services.author_resolver import resolve_author_debug
from services.meta_store import make_key, load_meta, update_meta_locked
from services.auto_fill_service import (
    VALID_SOURCES,
    VALID_MODES,
    get_auto_fill_state,
    start_auto_fill_job,
)

router = APIRouter()

# 同じ書籍を短時間に何度開いても view_count を膨らませない閾値（秒）
VIEW_COUNT_DEBOUNCE_SEC = 300


# ---------------------------------------------------------------------------
# リクエスト/レスポンスモデル
# ---------------------------------------------------------------------------

class BookMetaEntry(BaseModel):
    authors: list[str]


class UpdateMetaRequest(BaseModel):
    """単一書籍または複数書籍へのメタデータ更新リクエスト。

    `authors` / `tags` / `hidden` は省略可。省略されたフィールドは変更しない。
    すべて省略するとエラー（更新する内容が無い）。
    """
    path: str = ""
    names: list[str]
    authors: list[str] | None = None
    tags: list[str] | None = None
    hidden: bool | None = None
    source: str = "generated"


class RecordViewRequest(BaseModel):
    """閲覧記録リクエスト。"""
    path: str = ""
    name: str
    source: str = "generated"


# ---------------------------------------------------------------------------
# エンドポイント
# ---------------------------------------------------------------------------

@router.get("/meta")
def get_meta(source: str = "generated") -> dict:
    """
    指定ソースの meta.json 全体を返す。
    レスポンス: { "key": { "authors": [...] }, ... }
    """
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail="Invalid source")
    return load_meta(source)


@router.patch("/meta")
def update_meta(request: UpdateMetaRequest) -> dict:
    """1冊または複数冊のメタデータ（作者名 / タグ / 非表示フラグ）を上書き保存する。

    `authors` / `tags` / `hidden` は省略可。省略されたフィールドは変更しない。
    """
    if request.source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail="Invalid source")
    if request.authors is None and request.tags is None and request.hidden is None:
        raise HTTPException(status_code=400, detail="authors, tags, or hidden must be specified")

    validate_safe_path(request.path, param_name="path")
    for name in request.names:
        validate_safe_name(name, param_name="name")

    # 各フィールドを正規化（None ならそのまま）
    authors = [a.strip() for a in request.authors if a.strip()] if request.authors is not None else None
    tags = [t.strip() for t in request.tags if t.strip()] if request.tags is not None else None
    hidden = request.hidden  # bool | None

    def _merge_list_field(entry: dict, field: str, value: list[str] | None) -> None:
        """list フィールドを書き換える。`value is None` の場合は何もしない。"""
        if value is None:
            return
        if value:
            entry[field] = value
        else:
            # 空配列を渡された場合は空のまま残す（最後にエントリ自体を消すかは呼び出し側で判定）
            entry[field] = []

    def _merge_hidden(entry: dict, value: bool | None) -> None:
        """hidden フィールドを書き換えるか削除する。`value is None` の場合は何もしない。"""
        if value is None:
            return
        if value:
            entry["hidden"] = True
        else:
            entry.pop("hidden", None)

    def _apply(data):
        for name in request.names:
            key = make_key(request.path, name)
            existing = dict(data.get(key, {}))
            _merge_list_field(existing, "authors", authors)
            _merge_list_field(existing, "tags", tags)
            _merge_hidden(existing, hidden)

            # エントリ全体が「空 list だけ」「あるいは何も無い」場合は削除
            # 非 list フィールド（view_count / hidden 等）が残っていればエントリは保持
            has_meaningful = any(
                not (isinstance(v, list) and not v) for v in existing.values()
            )
            if has_meaningful:
                data[key] = existing
            else:
                data.pop(key, None)

    update_meta_locked(request.source, _apply)
    return {"message": "Updated", "updated_count": len(request.names)}


@router.post("/meta/view")
def record_view(request: RecordViewRequest) -> dict:
    """書籍の閲覧を記録する。

    - `last_viewed_at` は呼び出し毎に常に現在時刻で更新（最近見た順ソート用）。
    - `view_count` は前回 last_viewed_at から VIEW_COUNT_DEBOUNCE_SEC 以上経過した場合のみ +1。
      短時間で同じ書籍を何度も開いてもカウントが膨らまないようにする。
    """
    if request.source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail="Invalid source")

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
        data[key] = {**existing, "view_count": new_count, "last_viewed_at": now}
        result["view_count"] = new_count
        result["last_viewed_at"] = now
        result["incremented"] = should_increment

    update_meta_locked(request.source, _apply)
    return result


# ---------------------------------------------------------------------------
# 作者名自動登録ジョブ
# ---------------------------------------------------------------------------

@router.post("/meta/auto-fill")
def start_auto_fill(
    source: str = "generated",
    mode: str = "unknown_only",
) -> dict:
    """
    サークル名自動登録ジョブを開始する。
    - mode=missing_only : 作者名エントリが存在しない書籍のみ
    - mode=unknown_only : 「作者不明」の書籍のみ（デフォルト）
    - mode=overwrite_all: 登録済みを含む全件を上書き
    - 既にジョブが実行中の場合は 409 を返す。
    """
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail="Invalid source")
    if mode not in VALID_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Choose from: {', '.join(VALID_MODES)}")

    state = get_auto_fill_state(source)
    if state.status == "running":
        raise HTTPException(status_code=409, detail="Auto-fill job is already running")

    start_auto_fill_job(source, mode)
    return {"started": True, "source": source, "mode": mode}


@router.get("/meta/auto-fill/test")
def test_auto_fill(title: str, source: str = "generated") -> dict:
    """
    1件分のサークル名解決を実行し、各ステップの中間結果を返すデバッグ用エンドポイント。
    SearXNG の検索結果と Gemma の応答を確認するために使う。
    """
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail="Invalid source")
    return resolve_author_debug(title, source)


@router.get("/meta/auto-fill/status")
def get_auto_fill_status(source: str = "generated") -> dict:
    """作者名自動登録ジョブの進捗を返す。"""
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail="Invalid source")

    state = get_auto_fill_state(source)
    return {
        "status": state.status,
        "total": state.total,
        "done": state.done,
        "skipped": state.skipped,
        "current": state.current,
        "results": state.results,
        "error": state.error,
    }
