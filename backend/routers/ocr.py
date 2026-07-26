"""OCR ジョブルーター（job_queue ベース）。

旧 OCRService（Borg singleton + daemon thread）を廃止し、
novel.db の rebuild_jobs テーブルで OCR ジョブを一元管理する。

POST /ocr/run     — OCR ジョブをキューに追加
POST /ocr/stop    — キュー中の OCR ジョブをキャンセル
GET  /ocr/status  — OCR ジョブの状態（フロントエンド互換形式）
"""

import secrets

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import config
from routers.api_schemas import (
    OcrAgentActionResponse,
    OcrAgentClaimRequest,
    OcrAgentClaimResponse,
    OcrAgentFailRequest,
    OcrAgentHeartbeatRequest,
    OcrAgentPageSubmitRequest,
    OcrGroundTruthListResponse,
    OcrGroundTruthSeedRequest,
    OcrGroundTruthSeedResponse,
    OcrGroundTruthUpdateRequest,
    OcrPageTypeClassificationResponse,
    OcrQaActionResponse,
    OcrQaPageReviewRequest,
    OcrQaRunApproveRequest,
    OcrQaRunDetail,
    OcrQaRunListResponse,
    OcrRunResponse,
    OcrStopResponse,
)
from services.novel_db import ocr_agent_jobs
from services.novel_db.connection import with_db
from services.novel_db.job_queue import job_queue
from services.novel_db.ocr_ground_truth import (
    get_ground_truth_image_path,
    list_ground_truth,
    seed_ground_truth,
    update_ground_truth,
)
from services.novel_db.ocr_staging import (
    approve_and_publish_run,
    classify_run_pages,
    get_qa_image_path,
    get_qa_run,
    list_qa_runs,
    review_qa_page,
)
from utils.path_utils import validate_safe_name

router = APIRouter()


def _require_ocr_agent(x_capture_agent_token: str | None) -> None:
    if not config.app_settings.OCR_AGENT_ENABLED:
        raise HTTPException(status_code=503, detail="OCR agent is disabled")
    expected = config.KINDLE_CAPTURE_AGENT_TOKEN
    if not expected:
        raise HTTPException(status_code=503, detail="KINDLE_CAPTURE_AGENT_TOKEN が設定されていません")
    if not x_capture_agent_token or not secrets.compare_digest(x_capture_agent_token, expected):
        raise HTTPException(status_code=401, detail="OCRエージェント認証に失敗しました")


@router.post("/ocr/run", response_model=OcrRunResponse)
def run_ocr(target_dir: str | None = None) -> dict:
    if target_dir:
        validate_safe_name(target_dir, param_name="target_dir")
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


@router.post("/ocr/agents/claim", response_model=OcrAgentClaimResponse)
def claim_ocr_agent_job(
    request: OcrAgentClaimRequest,
    x_capture_agent_token: str | None = Header(default=None),
) -> dict:
    _require_ocr_agent(x_capture_agent_token)
    return {"job": ocr_agent_jobs.claim(request.agent_id)}


@router.get(
    "/ocr/agents/jobs/{job_id}/pages/{book_name}/{page_no}/image",
    response_class=FileResponse,
)
def get_ocr_agent_page_image(
    job_id: int,
    book_name: str,
    page_no: int,
    x_ocr_agent_id: str | None = Header(default=None),
    x_capture_agent_token: str | None = Header(default=None),
) -> FileResponse:
    _require_ocr_agent(x_capture_agent_token)
    if not x_ocr_agent_id:
        raise HTTPException(status_code=401, detail="X-OCR-Agent-ID が必要です")
    try:
        path = ocr_agent_jobs.image_path(job_id, x_ocr_agent_id, book_name, page_no)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return FileResponse(path, media_type="image/png")


@router.post("/ocr/agents/jobs/{job_id}/heartbeat", response_model=OcrAgentActionResponse)
def heartbeat_ocr_agent_job(
    job_id: int,
    request: OcrAgentHeartbeatRequest,
    x_capture_agent_token: str | None = Header(default=None),
) -> dict:
    _require_ocr_agent(x_capture_agent_token)
    try:
        return ocr_agent_jobs.heartbeat(job_id, request.agent_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/ocr/agents/jobs/{job_id}/pages", response_model=OcrAgentActionResponse)
def submit_ocr_agent_page(
    job_id: int,
    request: OcrAgentPageSubmitRequest,
    x_capture_agent_token: str | None = Header(default=None),
) -> dict:
    _require_ocr_agent(x_capture_agent_token)
    try:
        return ocr_agent_jobs.submit_page(
            job_id,
            request.agent_id,
            request.book_name,
            request.page.model_dump(),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/ocr/agents/jobs/{job_id}/complete", response_model=OcrAgentActionResponse)
def complete_ocr_agent_job(
    job_id: int,
    request: OcrAgentHeartbeatRequest,
    x_capture_agent_token: str | None = Header(default=None),
) -> dict:
    _require_ocr_agent(x_capture_agent_token)
    try:
        return ocr_agent_jobs.complete(job_id, request.agent_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/ocr/agents/jobs/{job_id}/fail", response_model=OcrAgentActionResponse)
def fail_ocr_agent_job(
    job_id: int,
    request: OcrAgentFailRequest,
    x_capture_agent_token: str | None = Header(default=None),
) -> dict:
    _require_ocr_agent(x_capture_agent_token)
    try:
        return ocr_agent_jobs.fail(job_id, request.agent_id, request.error)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/ocr/qa/runs", response_model=OcrQaRunListResponse)
def get_ocr_qa_runs() -> dict:
    return {"runs": list_qa_runs()}


@router.get("/ocr/qa/runs/{run_id}", response_model=OcrQaRunDetail)
def get_ocr_qa_run(run_id: int) -> dict:
    try:
        return get_qa_run(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/ocr/qa/runs/{run_id}/pages/{page_no}/image", response_class=FileResponse)
def get_ocr_qa_page_image(run_id: int, page_no: int) -> FileResponse:
    try:
        path = get_qa_image_path(run_id, page_no)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return FileResponse(path, media_type="image/png")


@router.patch("/ocr/qa/runs/{run_id}/pages/{page_no}", response_model=OcrQaActionResponse)
def review_ocr_qa_page(
    run_id: int,
    page_no: int,
    request: OcrQaPageReviewRequest,
) -> dict:
    try:
        review_qa_page(run_id, page_no, request.state, request.note, request.page_type)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": request.state, "run_id": run_id}


@router.post(
    "/ocr/qa/runs/{run_id}/classify-pages",
    response_model=OcrPageTypeClassificationResponse,
)
def classify_ocr_qa_pages(run_id: int) -> dict:
    try:
        counts = classify_run_pages(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "classified", "run_id": run_id, "counts": counts}


@router.post("/ocr/qa/runs/{run_id}/approve", response_model=OcrQaActionResponse)
def approve_ocr_qa_run(run_id: int, request: OcrQaRunApproveRequest) -> dict:
    reviewer = request.reviewer.strip()
    if not reviewer:
        raise HTTPException(status_code=422, detail="reviewer is required")
    try:
        approve_and_publish_run(run_id, reviewer, request.note)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "approved", "run_id": run_id}


@router.get("/ocr/ground-truth", response_model=OcrGroundTruthListResponse)
def get_ocr_ground_truth() -> dict:
    return list_ground_truth()


@router.post("/ocr/ground-truth/seed", response_model=OcrGroundTruthSeedResponse)
def seed_ocr_ground_truth(request: OcrGroundTruthSeedRequest) -> dict:
    try:
        created = seed_ground_truth(
            [{"run_id": sample.run_id, "page_no": sample.page_no} for sample in request.samples]
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "seeded", "created": created}


@router.patch("/ocr/ground-truth/{entry_id}", response_model=OcrGroundTruthListResponse)
def update_ocr_ground_truth(
    entry_id: int,
    request: OcrGroundTruthUpdateRequest,
) -> dict:
    try:
        update_ground_truth(
            entry_id,
            reference_text=request.reference_text,
            page_type=request.page_type,
            state=request.state,
            note=request.note,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return list_ground_truth()


@router.get("/ocr/ground-truth/{entry_id}/image", response_class=FileResponse)
def get_ocr_ground_truth_image(entry_id: int) -> FileResponse:
    try:
        path = get_ground_truth_image_path(entry_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return FileResponse(path, media_type="image/png")
