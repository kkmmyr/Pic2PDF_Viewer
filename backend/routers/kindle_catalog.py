"""Kindle 購入カタログ API。"""

import json
import secrets
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query

import config
from routers.api_schemas import (
    KindleAgentClaimResponse,
    KindleCaptureCompleteResponse,
    KindleCaptureHeartbeatResponse,
    KindleCaptureJobOut,
    KindleCaptureJobsResponse,
    KindleCatalogBooksResponse,
    KindleCatalogSourceStatusResponse,
    KindleCatalogStatsResponse,
    KindleImportRunsResponse,
    KindleLinkCandidatesResponse,
    KindleLinkResponse,
    KindleMigrationCommitResponse,
    KindleMigrationPreviewResponse,
    KindleOrdersImportResponse,
    KindleUnlinkedBooksResponse,
    KindleUnlinkResponse,
)
from routers.schemas.kindle_catalog import (
    AgentClaimRequest,
    AgentCompleteRequest,
    AgentHeartbeatRequest,
    AgentStateRequest,
    CaptureJobCreateRequest,
    LinkRequest,
    MigrationCommitRequest,
    UnlinkRequest,
)
from services.kindle_catalog import (
    capture_jobs,
    enrichment_imports,
    imports,
    legacy_source_status,
    links,
    repository,
)

router = APIRouter(prefix="/kindle-catalog")


def _require_agent_token(x_capture_agent_token: str | None = Header(default=None)) -> None:
    expected = config.KINDLE_CAPTURE_AGENT_TOKEN
    if not expected:
        raise HTTPException(status_code=503, detail="KINDLE_CAPTURE_AGENT_TOKEN が設定されていません")
    if not x_capture_agent_token or not secrets.compare_digest(x_capture_agent_token, expected):
        raise HTTPException(status_code=401, detail="キャプチャエージェント認証に失敗しました")


@router.get("/books", response_model=KindleCatalogBooksResponse)
def list_books(
    q: str | None = Query(default=None, max_length=200),
    book_type: Literal["comic", "novel", "other", "unknown"] | None = None,
    ownership: Literal["purchased", "borrowed_active", "borrowed_ended", "returned", "unknown"] | None = None,
    capture_state: Literal["not_captured", "captured", "multiple_links", "capture_pending"] | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    return repository.list_books(
        q=q,
        book_type=book_type,
        ownership=ownership,
        capture_state=capture_state,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=KindleCatalogStatsResponse)
def get_stats():
    return repository.stats()


@router.get("/imports/sources", response_model=KindleCatalogSourceStatusResponse)
def get_import_sources():
    return legacy_source_status.source_status()


@router.get("/imports/runs", response_model=KindleImportRunsResponse)
def get_import_runs(limit: int = Query(default=50, ge=1, le=200)):
    return {"items": repository.list_import_runs(limit)}


@router.post("/imports/orders", response_model=KindleOrdersImportResponse)
def import_orders():
    try:
        return imports.run_orders_import()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/imports/kindle-info", response_model=KindleOrdersImportResponse)
def import_kindle_info():
    try:
        return enrichment_imports.run_kindle_info_import()
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/imports/autobuy", response_model=KindleOrdersImportResponse)
def import_autobuy():
    try:
        return enrichment_imports.run_autobuy_import()
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/migration/preview", response_model=KindleMigrationPreviewResponse)
def preview_legacy_migration():
    from services.kindle_catalog import legacy_migration

    try:
        return legacy_migration.preview()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/migration/commit", response_model=KindleMigrationCommitResponse)
def commit_legacy_migration(request: MigrationCommitRequest):
    from services.kindle_catalog import legacy_migration

    try:
        return legacy_migration.commit(request.confirmation_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/links/unlinked", response_model=KindleUnlinkedBooksResponse)
def get_unlinked_books():
    return {"items": links.list_unlinked()}


@router.get("/links/candidates", response_model=KindleLinkCandidatesResponse)
def get_link_candidates(
    source: Literal["comic", "novel"],
    book_id: str = Query(max_length=500),
    limit: int = Query(default=10, ge=1, le=50),
):
    try:
        return {"items": links.candidates(source, book_id, limit)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/links", response_model=KindleLinkResponse)
def link_existing_book(request: LinkRequest):
    try:
        return links.link(request.source, request.book_id, request.asin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/links", response_model=KindleUnlinkResponse)
def unlink_existing_book(request: UnlinkRequest):
    try:
        return links.unlink(request.source, request.book_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/capture-jobs", response_model=KindleCaptureJobOut)
def create_capture_job(request: CaptureJobCreateRequest):
    if request.expected_screens is not None and not 1 <= request.expected_screens <= 5000:
        raise HTTPException(status_code=400, detail="expected_screens は 1〜5000 で指定してください")
    try:
        return capture_jobs.create(
            request.asin,
            request.source,
            request.direction,
            request.expected_screens,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/capture-jobs", response_model=KindleCaptureJobsResponse)
def get_capture_jobs(limit: int = Query(default=100, ge=1, le=500)):
    return {"items": capture_jobs.list_jobs(limit)}


@router.post(
    "/agents/claim",
    response_model=KindleAgentClaimResponse,
)
def claim_capture_job(
    request: AgentClaimRequest,
    x_capture_agent_token: str | None = Header(default=None),
):
    _require_agent_token(x_capture_agent_token)
    return {"job": capture_jobs.claim(request.agent_id)}


@router.post("/agents/jobs/{job_id}/state", response_model=KindleCaptureJobOut)
def update_capture_job_state(
    job_id: str,
    request: AgentStateRequest,
    x_capture_agent_token: str | None = Header(default=None),
):
    _require_agent_token(x_capture_agent_token)
    try:
        return capture_jobs.update_state(
            job_id,
            request.agent_id,
            request.state,
            captured_screens=request.captured_screens,
            error_code=request.error_code,
            error_message=request.error_message,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/agents/jobs/{job_id}/heartbeat",
    response_model=KindleCaptureHeartbeatResponse,
)
def heartbeat_capture_job(
    job_id: str,
    request: AgentHeartbeatRequest,
    x_capture_agent_token: str | None = Header(default=None),
):
    _require_agent_token(x_capture_agent_token)
    try:
        return capture_jobs.heartbeat(job_id, request.agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/agents/jobs/{job_id}/complete", response_model=KindleCaptureCompleteResponse)
def complete_capture_job(
    job_id: str,
    request: AgentCompleteRequest,
    x_capture_agent_token: str | None = Header(default=None),
):
    _require_agent_token(x_capture_agent_token)
    try:
        return capture_jobs.complete(job_id, request.agent_id)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
