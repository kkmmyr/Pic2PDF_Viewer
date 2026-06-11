"""novel_db 再構築ジョブエンドポイント（/builds/*）。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from routers._deps import cancel_job_response, log_and_raise_500
from routers.api_schemas import RebuildEnqueueResponse, RebuildStatusResponse
from services.novel_db.job_queue import job_queue

from .schemas import RebuildRequest

router = APIRouter()


@router.post("/builds", response_model=RebuildEnqueueResponse)
@log_and_raise_500("novel_db/builds")
def post_rebuild(request: RebuildRequest) -> dict:
    """再構築 / OCR ジョブをキューに登録する（[API §7.8]）。

    mode='rebuild': pages.full_text → chunk/embed を再構築（OCR 済み前提）
    mode='ocr':     images/*.png → OCR → pages.full_text を更新
    """
    if request.type in ("book", "series") and not request.target_id:
        raise HTTPException(
            status_code=422,
            detail=f"target_id is required for type='{request.type}'",
        )

    job_id, queued_position = job_queue.enqueue(request.type, request.target_id, request.mode)
    return {"job_id": job_id, "queued_position": queued_position}


@router.get("/builds/status", response_model=RebuildStatusResponse)
@log_and_raise_500("novel_db/builds/status")
def get_rebuild_status() -> dict:
    """現在のキュー状態を返す（[API §7.9]）。"""
    return job_queue.get_status()


@router.delete("/builds/{job_id}", status_code=204)
@log_and_raise_500("novel_db/builds/cancel")
def delete_rebuild(job_id: int) -> Response:
    """待機中ジョブをキャンセルする（[API §7.10]）。実行中は 409。"""
    return cancel_job_response(job_queue.cancel(job_id))
