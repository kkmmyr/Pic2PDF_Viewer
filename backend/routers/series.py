"""シリーズ自動グループ化ルーター。

`POST /api/series/resolve` でジョブ起動、`GET /api/series/resolve/status` で進捗取得。
auto-fill と同じ非同期ジョブパターン。
"""
from fastapi import APIRouter, HTTPException

from services.series_resolver import (
    VALID_SOURCES,
    get_state,
    start_resolve_job,
)

router = APIRouter()


@router.post("/series/resolve")
def start_series_resolve(source: str = "generated", use_gemma: bool = False) -> dict:
    """シリーズ判定ジョブを起動する。

    `use_gemma=true` を指定すると、ルール判定後に Gemma で曖昧ケースを再評価する。
    """
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail="Invalid source")

    state = get_state(source)
    if state.status == "running":
        raise HTTPException(status_code=409, detail="Series resolve job is already running")

    start_resolve_job(source, use_gemma=use_gemma)
    return {"started": True, "source": source, "use_gemma": use_gemma}


@router.get("/series/resolve/status")
def get_series_resolve_status(source: str = "generated") -> dict:
    """シリーズ判定ジョブの進捗を返す。"""
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail="Invalid source")

    state = get_state(source)
    return {
        "status": state.status,
        "total": state.total,
        "done": state.done,
        "created": state.created,
        "current": state.current,
        "error": state.error,
    }
