"""novel_db 質問応答（SSE）+ 履歴エンドポイント。"""

from __future__ import annotations

import asyncio
from contextlib import aclosing

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from config import NOVEL_DB_LLM_MODEL
from config.novel_db import novel_db_settings
from routers._deps import log_and_raise_500, sse_event
from routers.api_schemas import QaHistoryDetailResponse, QaHistoryResponse
from services.novel_db import Scope, with_db
from services.novel_db.llm import stream_qa
from services.novel_db.prompt_builder import build_prompt
from services.novel_db.qa_grounding import build_grounded_prompt, stream_verified_quotes
from services.novel_db.qa_history import (
    delete_history,
    get_history_detail,
    list_history,
    save_error,
    save_finish,
    save_start,
)
from services.novel_db.qa_source_snapshot import assert_qa_sources_current, freeze_qa_sources
from services.novel_db.retrieval import RagNotReady, retrieve
from utils.logger import get_logger

from ._deps import require_not_locked
from .schemas import QaRequest

router = APIRouter()
logger = get_logger(__name__)


@router.post("/qa")
async def post_qa(
    request: QaRequest,
    http_request: Request,
    _: None = Depends(require_not_locked),
) -> StreamingResponse:
    """RAG 質問応答を SSE で返す（[API §7.4]）。"""
    scope = Scope(type=request.scope.type, id=request.scope.id)
    verified_quotes = novel_db_settings.NOVEL_DB_QA_RESPONSE_MODE == "verified_quotes"
    snapshot = None

    with with_db() as conn:
        try:
            result = retrieve(conn, request.question, scope)
        except RagNotReady as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if verified_quotes:
            snapshot = freeze_qa_sources(conn, result.hits)
            prompt = build_grounded_prompt(request.question, snapshot.sources)
        else:
            prompt = build_prompt(
                request.question,
                result.hits,
                scope,
                book_summaries=result.book_summaries,
            )
        qa_options = dict(result.qa_options)
        if snapshot is not None:
            qa_options.update(qa_response_mode="verified_quotes", qa_body_versions=snapshot.body_versions)
        history_id = save_start(
            conn,
            scope=scope,
            question=request.question,
            prompt=prompt,
            hits=result.hits,
            model=NOVEL_DB_LLM_MODEL,
            options=qa_options,
        )

    async def event_stream():
        full_response: list[str] = []
        finished = False
        events = (
            stream_verified_quotes(prompt, snapshot.sources, model=NOVEL_DB_LLM_MODEL, options=qa_options)
            if snapshot is not None
            else stream_qa(prompt, options=qa_options)
        )
        try:
            async with aclosing(events):
                async for event in events:
                    if await http_request.is_disconnected():
                        with with_db() as conn:
                            save_finish(
                                conn,
                                history_id,
                                answer="".join(full_response) if snapshot is None else "",
                                done_reason="canceled",
                                eval_count=None,
                            )
                        finished = True
                        return
                    if event.get("pending"):
                        yield ": keep-alive\n\n"
                        continue
                    if event.get("response"):
                        full_response.append(event["response"])
                        if snapshot is None:
                            yield sse_event({"token": event["response"]})
                    if event.get("done"):
                        answer = "".join(full_response)
                        done_reason = event.get("done_reason", "stop")
                        eval_count = event.get("eval_count")
                        with with_db() as conn:
                            if snapshot is not None:
                                conn.execute("BEGIN IMMEDIATE")
                                assert_qa_sources_current(conn, snapshot)
                            save_finish(
                                conn,
                                history_id,
                                answer=answer,
                                done_reason=done_reason,
                                eval_count=eval_count,
                                validation_attempts=event.get("validation_attempts"),
                            )
                        finished = True
                        if snapshot is not None:
                            yield sse_event({"token": answer})
                        yield sse_event(
                            {
                                "done": True,
                                "history_id": history_id,
                                "eval_count": eval_count,
                                "done_reason": done_reason,
                            }
                        )
                        return
        except asyncio.CancelledError:
            if not finished:
                with with_db() as conn:
                    save_finish(
                        conn,
                        history_id,
                        answer="".join(full_response) if snapshot is None else "",
                        done_reason="canceled",
                        eval_count=None,
                    )
            raise
        except Exception as e:
            logger.exception("post_qa SSE failed")
            with with_db() as conn:
                save_error(conn, history_id, str(e))
            yield sse_event({"error": str(e)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# 履歴
# ---------------------------------------------------------------------------


@router.get("/qa/history", response_model=QaHistoryResponse)
@log_and_raise_500("novel_db/qa/history")
def get_qa_history(offset: int = 0, limit: int = 20, book: str | None = None) -> dict:
    """履歴一覧（[API §7.5]）。book 指定時はその書籍の質問のみ返す。"""
    if offset < 0 or limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="invalid offset/limit")
    with with_db() as conn:
        return list_history(conn, offset=offset, limit=limit, book=book)


@router.get("/qa/history/{history_id}", response_model=QaHistoryDetailResponse)
@log_and_raise_500("novel_db/qa/history/detail")
def get_qa_history_detail(history_id: int) -> dict:
    """履歴詳細（[API §7.6]）。"""
    with with_db() as conn:
        detail = get_history_detail(conn, history_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="history not found")
    return detail


@router.delete("/qa/history/{history_id}", status_code=204)
@log_and_raise_500("novel_db/qa/history/delete")
def delete_qa_history(history_id: int) -> Response:
    """履歴削除（[API §7.7]）。"""
    with with_db() as conn:
        ok = delete_history(conn, history_id)
    if not ok:
        raise HTTPException(status_code=404, detail="history not found")
    return Response(status_code=204)
