"""OCR ジョブルーター（job_queue ベース）。

旧 OCRService（Borg singleton + daemon thread）を廃止し、
novel.db の rebuild_jobs テーブルで OCR ジョブを一元管理する。

POST /ocr/run     — OCR ジョブをキューに追加
POST /ocr/stop    — キュー中の OCR ジョブをキャンセル
GET  /ocr/status  — OCR ジョブの状態（フロントエンド互換形式）
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from routers.api_schemas import OcrRunResponse, OcrStopResponse
from services.novel_db.connection import with_db
from services.novel_db.job_queue import job_queue

router = APIRouter()


@router.post("/ocr/run", response_model=OcrRunResponse)
def run_ocr(target_dir: str | None = None) -> dict:
    if target_dir:
        job_id, position = job_queue.enqueue("book", target_id=target_dir, mode="ocr")
    else:
        job_id, position = job_queue.enqueue("all", mode="ocr")
    return {"status": "queued", "job_id": job_id, "queue_position": position}


@router.post("/ocr/stop", response_model=OcrStopResponse)
def stop_ocr() -> dict:
    canceled = job_queue.cancel_queued_by_mode("ocr")
    if not canceled:
        raise HTTPException(status_code=400, detail="No queued OCR jobs to cancel")
    return {"status": "canceled", "canceled_jobs": canceled}


class StatusResponse(BaseModel):
    status: str
    last_return_code: int | None
    logs: list[str]


@router.get("/ocr/status", response_model=StatusResponse)
def get_ocr_status():
    """OCR ジョブの状態をフロントエンド互換形式で返す。

    rebuild_jobs から OCR 専用行を抽出し、旧 OCRService と同じスキーマ
    (status / logs / last_return_code) に変換して返す。
    """
    with with_db() as conn:
        running = conn.execute(
            "SELECT current_step, current_detail, progress_total, progress_done "
            "FROM rebuild_jobs WHERE state='running' AND mode='ocr' "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        queued_count = conn.execute("SELECT COUNT(*) FROM rebuild_jobs WHERE state='queued' AND mode='ocr'").fetchone()[
            0
        ]
        last_done = conn.execute(
            "SELECT state, error_message FROM rebuild_jobs "
            "WHERE mode='ocr' AND state IN ('completed', 'failed') "
            "ORDER BY finished_at DESC LIMIT 1"
        ).fetchone()

    logs: list[str] = []
    if running:
        step, detail, total, done = running
        if step:
            logs.append(step)
        if detail:
            logs.append(detail)
        if total is not None and done is not None:
            logs.append(f"進捗: {done}/{total}")
        return {"status": "running", "last_return_code": None, "logs": logs}
    if queued_count > 0:
        logs.append(f"キュー中: {queued_count} ジョブ")
        return {"status": "running", "last_return_code": None, "logs": logs}
    if last_done:
        last_state, error_message = last_done
        if last_state == "completed":
            return {"status": "idle", "last_return_code": 0, "logs": []}
        logs.append(error_message[:200] if error_message else "OCR failed")
        return {"status": "error", "last_return_code": 1, "logs": logs}
    return {"status": "idle", "last_return_code": None, "logs": []}
