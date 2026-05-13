"""B-20 読書会ディスカッション生成 API ルーター。

POST /api/novel/discussion/generate  → SSE ストリーミング
GET  /api/novel/discussion/history   → 過去生成一覧（?book_name=<name>）
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import NOVEL_DB_BODY_PAGE_MARGIN, NOVEL_DB_MIN_BODY_CHARS
from routers._deps import sse_event
from utils.logger import get_logger
from services.novel_db.connection import with_db
from services.novel_db.discussion_service import (
    MAX_INPUT_TOKENS,
    Persona,
    build_messages,
    estimate_book_tokens,
    list_discussions,
    save_discussion,
    stream_discussion_turns,
)
from services.novel_db.search import load_all_pages_of_book

router = APIRouter()
logger = get_logger(__name__)


class PersonaRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    style_description: str = Field(..., min_length=1, max_length=200)


class GenerateRequest(BaseModel):
    book_name: str = Field(..., min_length=1)
    personas: list[PersonaRequest] = Field(..., min_length=2, max_length=2)
    num_turns: int = Field(default=6, ge=2, le=20)


@router.post("/novel/discussion/generate")
async def generate_discussion(
    request: GenerateRequest,
    http_request: Request,
) -> StreamingResponse:
    """読書会ディスカッションを SSE でストリーミング生成する（B-20）。"""
    persona_a = Persona(
        name=request.personas[0].name,
        style_description=request.personas[0].style_description,
    )
    persona_b = Persona(
        name=request.personas[1].name,
        style_description=request.personas[1].style_description,
    )

    with with_db() as conn:
        hits = load_all_pages_of_book(
            conn,
            request.book_name,
            min_chars=NOVEL_DB_MIN_BODY_CHARS,
            body_page_margin=NOVEL_DB_BODY_PAGE_MARGIN,
        )

    if not hits:
        async def _no_pages() -> AsyncGenerator[str, None]:
            yield sse_event({
                "type": "error",
                "message": f"書籍「{request.book_name}」のページデータが見つかりません。インデックスを再構築してください。",
            })
        return StreamingResponse(_no_pages(), media_type="text/event-stream")

    token_count = estimate_book_tokens(hits)
    if token_count > MAX_INPUT_TOKENS:
        async def _too_long() -> AsyncGenerator[str, None]:
            yield sse_event({
                "type": "error",
                "message": (
                    f"本文が長すぎます（推定 {token_count:,} トークン、"
                    f"上限 {MAX_INPUT_TOKENS:,} トークン）。"
                ),
            })
        return StreamingResponse(_too_long(), media_type="text/event-stream")

    messages = build_messages(
        request.book_name, persona_a, persona_b, request.num_turns, hits,
    )

    async def event_stream() -> AsyncGenerator[str, None]:
        accumulated_turns: list[dict] = []
        try:
            async for turn_event in stream_discussion_turns(messages):
                if await http_request.is_disconnected():
                    return
                accumulated_turns.append({
                    "speaker": turn_event["speaker"],
                    "text": turn_event["text"],
                })
                yield sse_event(turn_event)
        except Exception as e:
            logger.exception("generate_discussion SSE failed")
            yield sse_event({"type": "error", "message": str(e)})
            return

        if accumulated_turns:
            saved_path = save_discussion(
                request.book_name, persona_a, persona_b, accumulated_turns,
            )
            yield sse_event({"type": "done", "saved_path": saved_path})
        else:
            yield sse_event({"type": "done"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/novel/discussion/history")
def get_discussion_history(book_name: str) -> list[dict]:
    """指定書籍のディスカッション履歴一覧を返す（B-20）。"""
    return list_discussions(book_name)
