"""4.6 本構築専用管理画面 API ルーター。

POST   /api/novel/build/enqueue         — Full Build ジョブ登録
GET    /api/novel/build/status          — キュー状態スナップショット（full_build のみ）
DELETE /api/novel/build/jobs/{job_id}   — 待機中ジョブキャンセル
GET    /api/novel/build/stream          — キュー状態 SSE ストリーム（API §8）
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from routers._deps import cancel_job_response, log_and_raise_500, sse_event
from utils.logger import get_logger
from services.novel_db.connection import with_db
from services.novel_db.job_queue import job_queue

router = APIRouter()
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# リクエスト / レスポンスモデル
# ---------------------------------------------------------------------------

class EnqueueRequest(BaseModel):
    book_name: str | None = Field(default=None)
    all_books: bool = Field(default=False)


# ---------------------------------------------------------------------------
# ヘルパー: full_build ジョブに絞ったステータス取得
# ---------------------------------------------------------------------------

def _get_full_build_status() -> dict:
    """job_queue の get_status() を full_build mode に絞って返す。"""
    raw = job_queue.get_status()

    current = raw["current_job"]
    if current and current.get("mode") != "full_build":
        current = None

    queued = [j for j in raw["queued_jobs"] if j.get("mode") == "full_build"]

    with with_db() as conn:
        recent_rows = conn.execute(
            "SELECT id, target_id, state, finished_at, error_message "
            "FROM rebuild_jobs "
            "WHERE mode='full_build' AND state IN ('completed','failed','canceled') "
            "ORDER BY finished_at DESC LIMIT 20"
        ).fetchall()

    recent = [
        {
            "id": r[0],
            "target_id": r[1],
            "state": r[2],
            "finished_at": r[3],
            "error_message": r[4],
        }
        for r in recent_rows
    ]

    return {
        "is_running": current is not None,
        "current_job": current,
        "queued_jobs": queued,
        "recent_finished": recent,
    }


def _is_already_queued_or_running(book_name: str | None) -> bool:
    """同一書籍（または全冊）の full_build ジョブがキュー / 実行中かチェックする。"""
    with with_db() as conn:
        if book_name is None:
            # 全冊ジョブ: type='all' の full_build が active ならブロック
            row = conn.execute(
                "SELECT 1 FROM rebuild_jobs "
                "WHERE mode='full_build' AND job_type='all' "
                "AND state IN ('queued','running') LIMIT 1"
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT 1 FROM rebuild_jobs "
                "WHERE mode='full_build' AND target_id=? "
                "AND state IN ('queued','running') LIMIT 1",
                (book_name,),
            ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# エンドポイント
# ---------------------------------------------------------------------------

@router.post("/novel/build/enqueue")
@log_and_raise_500("novel/build/enqueue")
def post_enqueue(request: EnqueueRequest) -> dict:
    """Full Build ジョブをキューに登録する（API §8.1）。"""
    if not request.all_books and not request.book_name:
        raise HTTPException(
            status_code=422, detail="book_name is required when all_books=false"
        )

    target_book = None if request.all_books else request.book_name

    if _is_already_queued_or_running(target_book):
        raise HTTPException(
            status_code=422, detail="already queued or running"
        )

    job_type = "all" if request.all_books else "book"
    job_id, queued_position = job_queue.enqueue(job_type, target_book, "full_build")
    return {"job_id": job_id, "queued_position": queued_position}


@router.get("/novel/build/status")
@log_and_raise_500("novel/build/status")
def get_status() -> dict:
    """Full Build キュー状態を返す（API §8.2）。"""
    return _get_full_build_status()


@router.delete("/novel/build/jobs/{job_id}", status_code=204)
@log_and_raise_500("novel/build/cancel")
def delete_job(job_id: int) -> Response:
    """待機中 Full Build ジョブをキャンセルする（API §8.3）。"""
    return cancel_job_response(job_queue.cancel(job_id))


@router.get("/novel/build/stream")
async def get_stream(http_request: Request) -> StreamingResponse:
    """Full Build キュー状態を SSE でストリーミングする（API §8.4）。

    @log_and_raise_500 非適用: HTTP ヘッダー送信後のストリーム内例外は
    SSE で配信してストリームを閉じる。クライアント側は再接続する。
    """

    async def event_stream():
        try:
            while True:
                if await http_request.is_disconnected():
                    break
                yield sse_event(_get_full_build_status())
                await asyncio.sleep(1.5)
        except Exception:
            logger.exception("novel/build/stream SSE failed")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
