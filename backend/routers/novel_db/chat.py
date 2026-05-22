"""novel_db マルチターン会話 QA セッションエンドポイント（B-16）。

パス: /sessions/* （旧: /qa/sessions/*）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from config import NOVEL_DB_QA_FULL_BOOK_MODE, NOVEL_DB_QA_FULL_BOOK_NUM_CTX
from routers._deps import log_and_raise_500, sse_event
from services.novel_db import Scope, with_db
from services.novel_db.llm import LLM_OPTIONS, stream_chat
from services.novel_db.prompt_builder import (
    build_chat_context_block,
    build_chat_system_message,
)
from services.novel_db.qa_sessions import (
    append_message,
    create_session,
    delete_session,
    get_session_detail,
    list_sessions,
    load_chat_messages,
    update_session_title,
)
from services.novel_db.retrieval import retrieve
from utils.logger import get_logger

from ._deps import require_not_locked
from .schemas import (
    ChatMessagePayload,
    ChatSessionContinueRequest,
    ChatSessionDetailPayload,
    ChatSessionStartRequest,
    ChatSessionSummary,
)

router = APIRouter()
logger = get_logger(__name__)


def _auto_title(question: str) -> str:
    """初手質問からセッションタイトルを生成する（先頭 30 字 + 省略記号）。"""
    text = question.strip().replace("\n", " ")
    if len(text) > 30:
        return text[:30] + "…"
    return text


async def _chat_event_stream(
    http_request: Request,
    session_id: int,
    messages: list[dict],
    qa_options: dict,
):
    """messages を Qwen に流して SSE で配信し、終端で assistant を DB 保存する。"""
    full_response: list[str] = []
    try:
        async for event in stream_chat(messages, options=qa_options):
            if await http_request.is_disconnected():
                with with_db() as conn:
                    append_message(
                        conn, session_id, role="assistant",
                        content="".join(full_response),
                        done_reason="canceled",
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
                    msg_id = append_message(
                        conn, session_id, role="assistant",
                        content=answer,
                        eval_count=eval_count, done_reason=done_reason,
                    )
                yield sse_event({
                    "done": True,
                    "session_id": session_id,
                    "message_id": msg_id,
                    "eval_count": eval_count,
                    "done_reason": done_reason,
                })
                return
    except NotImplementedError as e:
        with with_db() as conn:
            append_message(
                conn, session_id, role="assistant",
                content=f"backend does not support multi-turn chat: {e}",
                done_reason="error",
            )
        yield sse_event({"error": f"backend not supported: {e}"})
    except Exception as e:  # noqa: BLE001
        logger.exception("chat SSE failed")
        with with_db() as conn:
            append_message(
                conn, session_id, role="assistant",
                content=str(e), done_reason="error",
            )
        yield sse_event({"error": str(e)})


@router.get("/sessions")
@log_and_raise_500("novel_db/sessions")
def get_chat_sessions(
    offset: int = 0,
    limit: int = 20,
    scope_type: str | None = None,
    scope_id: str | None = None,
) -> list[ChatSessionSummary]:
    """会話セッション一覧（B-16）。scope_type / scope_id で絞り込み可能。"""
    if offset < 0 or limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="invalid offset/limit")
    with with_db() as conn:
        rows = list_sessions(conn, offset=offset, limit=limit, scope_type=scope_type, scope_id=scope_id)
    return [
        ChatSessionSummary(
            id=r.id, scope_type=r.scope_type, scope_id=r.scope_id,
            title=r.title, started_at=r.started_at,
            last_message_at=r.last_message_at, message_count=r.message_count,
        )
        for r in rows
    ]


@router.get("/sessions/{session_id}")
@log_and_raise_500("novel_db/sessions/detail")
def get_chat_session(session_id: int) -> ChatSessionDetailPayload:
    """会話セッション詳細（メッセージ全件含む、system は除外）（B-16）。

    UI は user/assistant のみを表示する。system は LLM 投入用の内部メッセージ
    なのでレスポンスから除外する。
    """
    with with_db() as conn:
        detail = get_session_detail(conn, session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="session not found")
    return ChatSessionDetailPayload(
        id=detail.id, scope_type=detail.scope_type, scope_id=detail.scope_id,
        title=detail.title, started_at=detail.started_at,
        last_message_at=detail.last_message_at,
        messages=[
            ChatMessagePayload(
                id=m.id, role=m.role, content=m.content,
                eval_count=m.eval_count, done_reason=m.done_reason,
                created_at=m.created_at,
            )
            for m in detail.messages if m.role != "system"
        ],
    )


@router.delete("/sessions/{session_id}", status_code=204)
@log_and_raise_500("novel_db/sessions/delete")
def delete_chat_session(session_id: int) -> Response:
    """会話セッション削除（メッセージは CASCADE で連動削除）（B-16）。"""
    with with_db() as conn:
        ok = delete_session(conn, session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    return Response(status_code=204)


@router.post("/sessions")
async def post_chat_session_start(
    request: ChatSessionStartRequest,
    http_request: Request,
    _: None = Depends(require_not_locked),
) -> StreamingResponse:
    """会話セッション開始 + 初手 SSE（B-16）。

    1. session 作成 + system / user メッセージを DB に append
    2. stream_chat に [system, user] を投入し、token を SSE で配信
    3. 終端で assistant メッセージを DB に append
    """
    scope = Scope(type=request.scope.type, id=request.scope.id)

    with with_db() as conn:
        result = retrieve(conn, request.question, scope)
        context_block = build_chat_context_block(
            result.hits, scope, book_summaries=result.book_summaries,
        )
        system_message = build_chat_system_message(
            scope, context_block=context_block,
        )
        session_id = create_session(conn, scope, title=_auto_title(request.question))
        append_message(conn, session_id, role="system", content=system_message)
        append_message(conn, session_id, role="user", content=request.question)
    qa_options = result.qa_options

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": request.question},
    ]
    return StreamingResponse(
        _chat_event_stream(http_request, session_id, messages, qa_options),
        media_type="text/event-stream",
    )


@router.post("/sessions/{session_id}/messages")
async def post_chat_session_message(
    session_id: int,
    request: ChatSessionContinueRequest,
    http_request: Request,
    _: None = Depends(require_not_locked),
) -> StreamingResponse:
    """会話セッションへの追加ターン SSE（B-16）。

    1. 既存 messages（system + user/assistant 履歴）を取得
    2. 新規 user メッセージを DB に append
    3. messages + new user を投入し SSE で配信
    4. 終端で assistant メッセージを DB に append
    """
    with with_db() as conn:
        detail = get_session_detail(conn, session_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="session not found")
        prior = load_chat_messages(conn, session_id)
        append_message(conn, session_id, role="user", content=request.question)

    messages = prior + [{"role": "user", "content": request.question}]
    qa_options = LLM_OPTIONS
    if detail.scope_type == "book" and NOVEL_DB_QA_FULL_BOOK_MODE:
        qa_options = {**LLM_OPTIONS, "num_ctx": NOVEL_DB_QA_FULL_BOOK_NUM_CTX}
    return StreamingResponse(
        _chat_event_stream(http_request, session_id, messages, qa_options),
        media_type="text/event-stream",
    )


@router.patch("/sessions/{session_id}/title")
@log_and_raise_500("novel_db/sessions/title")
def patch_chat_session_title(session_id: int, payload: dict) -> Response:
    """セッションタイトルを手動更新する（B-16）。"""
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="title is required")
    if len(title) > 100:
        raise HTTPException(status_code=422, detail="title too long (max 100)")
    with with_db() as conn:
        meta = get_session_detail(conn, session_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="session not found")
        update_session_title(conn, session_id, title)
    return Response(status_code=204)
