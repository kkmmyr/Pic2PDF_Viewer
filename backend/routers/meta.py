"""
書籍メタデータ管理ルーター。

各ソースの meta.json に作者名などを保存・取得する。
保存先: backend/data/meta/{source}/meta.json
キー: "{path}/{filename}" の相対パス（path が空の場合は "{filename}"）
"""
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


# ---------------------------------------------------------------------------
# リクエスト/レスポンスモデル
# ---------------------------------------------------------------------------

class BookMetaEntry(BaseModel):
    authors: list[str]


class UpdateMetaRequest(BaseModel):
    """単一書籍または複数書籍へのメタデータ更新リクエスト。"""
    path: str = ""
    names: list[str]
    authors: list[str]
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
    """1冊または複数冊の著者名を上書き保存する。"""
    if request.source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail="Invalid source")

    validate_safe_path(request.path, param_name="path")
    for name in request.names:
        validate_safe_name(name, param_name="name")

    authors = [a.strip() for a in request.authors if a.strip()]

    def _apply(data):
        for name in request.names:
            key = make_key(request.path, name)
            if authors:
                data[key] = {"authors": authors}
            else:
                data.pop(key, None)

    update_meta_locked(request.source, _apply)
    return {"message": "Updated", "updated_count": len(request.names)}


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
