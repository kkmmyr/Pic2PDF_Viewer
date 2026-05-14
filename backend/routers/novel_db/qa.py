"""novel_db 質問応答（SSE）+ 履歴エンドポイント。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from config import NOVEL_DB_LLM_MODEL
from routers._deps import log_and_raise_500, sse_event
from services.novel_db import Scope, with_db
from services.novel_db.llm import build_prompt, stream_qa
from services.novel_db.qa_history import (
    delete_history,
    get_history_detail,
    list_history,
    save_error,
    save_finish,
    save_start,
)
from services.novel_db.retrieval import retrieve
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

    with with_db() as conn:
        result = retrieve(conn, request.question, scope)
        prompt = build_prompt(
            request.question, result.hits, scope, book_summaries=result.book_summaries,
        )
        history_id = save_start(
            conn,
            scope=scope,
            question=request.question,
            prompt=prompt,
            hits=result.hits,
            model=NOVEL_DB_LLM_MODEL,
            options=result.qa_options,
        )
    qa_options = result.qa_options

    async def event_stream():
        full_response: list[str] = []
        try:
            async for event in stream_qa(prompt, options=qa_options):
                if await http_request.is_disconnected():
                    with with_db() as conn:
                        save_finish(
                            conn,
                            history_id,
                            answer="".join(full_response),
                            done_reason="canceled",
                            eval_count=None,
                        )
                    return
                if event.get("response"):
                    full_response.append(event["response"])
                    yield sse_event({"token": event["response"]})
                if event.get("done"):
                    answer = "".join(full_response)
                    done_reason = event.get("done_reason", "stop")
                    eval_count = event.get("eval_count")
                    with with_db() as conn:
                        save_finish(
                            conn,
                            history_id,
                            answer=answer,
                            done_reason=done_reason,
                            eval_count=eval_count,
                        )
                    yield sse_event({
                        "done": True,
                        "history_id": history_id,
                        "eval_count": eval_count,
                        "done_reason": done_reason,
                    })
                    return
        except Exception as e:
            logger.exception("post_qa SSE failed")
            with with_db() as conn:
                save_error(conn, history_id, str(e))
            yield sse_event({"error": str(e)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# 履歴
# ---------------------------------------------------------------------------

@router.get("/qa/history")
@log_and_raise_500("novel_db/qa/history")
def get_qa_history(offset: int = 0, limit: int = 20, book: str | None = None) -> dict:
    """履歴一覧（[API §7.5]）。book 指定時はその書籍の質問のみ返す。"""
    if offset < 0 or limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="invalid offset/limit")
    with with_db() as conn:
        return list_history(conn, offset=offset, limit=limit, book=book)


@router.get("/qa/history/{history_id}")
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
