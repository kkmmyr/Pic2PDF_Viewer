"""
書籍メタデータ管理ルーター。

各ソースの meta.json に作者名などを保存・取得する。
保存先: backend/data/meta/{source}/meta.json
キー: "{path}/{filename}" の相対パス（path が空の場合は "{filename}"）
"""
import json
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from routers._deps import assert_valid_source, validate_request_targets, validated_source
from services.author_resolver import resolve_author_debug
from services.auto_fill_service import (
    VALID_MODES,
    get_auto_fill_state,
    start_auto_fill_job,
)
from services.meta_store import (
    VALID_READ_STATES,
    has_meaningful_value,
    load_meta,
    make_key,
    merge_entry_fields,
    update_meta_locked,
)
from utils.path_utils import validate_safe_name, validate_safe_path

router = APIRouter()

# 同じ書籍を短時間に何度開いても view_count を膨らませない閾値（秒）
VIEW_COUNT_DEBOUNCE_SEC = 300


# ---------------------------------------------------------------------------
# リクエスト/レスポンスモデル
# ---------------------------------------------------------------------------

class UpdateMetaRequest(BaseModel):
    """単一書籍または複数書籍へのメタデータ更新リクエスト。

    `authors` / `tags` / `hidden` / `genre` / `read_state` は省略可。省略されたフィールドは変更しない。
    すべて省略するとエラー（更新する内容が無い）。
    """
    path: str = ""
    names: list[str]
    authors: list[str] | None = None
    tags: list[str] | None = None
    hidden: bool | None = None
    genre: str | None = None
    read_state: str | None = None
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
    date_str = datetime.now().strftime("%Y%m%d")
    filename = f"meta_{source}_{date_str}.json"
    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/meta")
def update_meta(request: UpdateMetaRequest) -> dict:
    """1冊または複数冊のメタデータ（作者名 / タグ / 非表示フラグ / ジャンル）を上書き保存する。

    指定したフィールドのみ書き換え、省略されたフィールドは保持する。
    すべての list フィールドが空になった場合はエントリ自体を削除する。
    """
    assert_valid_source(request.source)
    if (
        request.authors is None
        and request.tags is None
        and request.hidden is None
        and request.genre is None
        and request.read_state is None
    ):
        raise HTTPException(
            status_code=400,
            detail="authors, tags, hidden, genre, or read_state must be specified",
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
    tags = [t.strip() for t in request.tags if t.strip()] if request.tags is not None else None
    genre = request.genre.strip() if request.genre is not None else None

    def _apply(data):
        for name in request.names:
            key = make_key(request.path, name)
            merged = merge_entry_fields(
                data.get(key, {}),
                authors=authors,
                tags=tags,
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


# ---------------------------------------------------------------------------
# 作者名自動登録ジョブ
# ---------------------------------------------------------------------------

@router.post("/meta/auto-fill")
def start_auto_fill(
    source: str = Depends(validated_source),
    mode: str = "unknown_only",
) -> dict:
    """
    サークル名自動登録ジョブを開始する。
    - mode=missing_only : 作者名エントリが存在しない書籍のみ
    - mode=unknown_only : 「作者不明」の書籍のみ（デフォルト）
    - mode=overwrite_all: 登録済みを含む全件を上書き
    - 既にジョブが実行中の場合は 409 を返す。
    """
    if mode not in VALID_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Choose from: {', '.join(VALID_MODES)}")

    state = get_auto_fill_state(source)
    if state.status == "running":
        raise HTTPException(status_code=409, detail="Auto-fill job is already running")

    start_auto_fill_job(source, mode)
    return {"started": True, "source": source, "mode": mode}


@router.get("/meta/auto-fill/test")
def test_auto_fill(title: str, source: str = Depends(validated_source)) -> dict:
    """
    1件分のサークル名解決を実行し、各ステップの中間結果を返すデバッグ用エンドポイント。
    SearXNG の検索結果と Gemma の応答を確認するために使う。
    """
    return resolve_author_debug(title, source)


@router.get("/meta/auto-fill/status")
def get_auto_fill_status(source: str = Depends(validated_source)) -> dict:
    """作者名自動登録ジョブの進捗を返す。"""
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
