"""B-28 読書会ロングフォーム生成 API ルーター（B-20 を置き換え）。

POST   /api/novel/discussion/generate             → SSE ストリーミング（構成→台本の 2 段生成）
GET    /api/novel/discussion/history              → 過去生成一覧（?book_name=<name>）
DELETE /api/novel/discussion/history/{filename}   → 履歴削除（?book_name=<name>）
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from routers._deps import sse_event
from routers.api_schemas import DiscussionDeleteOut, DiscussionHistoryItemOut
from services.novel_db.discussion_service import (
    delete_discussion,
    list_discussions,
    prepare_discussion,
)
from utils.path_utils import validate_safe_name

router = APIRouter()


class GenerateRequest(BaseModel):
    book_name: str = Field(..., min_length=1)


@router.post("/novel/discussion/generate")
async def generate_discussion(
    request: GenerateRequest,
    http_request: Request,
) -> StreamingResponse:
    """読書会番組台本を SSE でストリーミング生成する（B-28）。

    構成ステップ（planning）→ 台本ステップ（scripting）の 2 段 LLM 呼び出し。
    完了時に DoD 機械チェック（M1〜M5）を実行し done イベントに含める。
    """
    validate_safe_name(request.book_name, param_name="book_name")
    events = prepare_discussion(request.book_name, is_disconnected=http_request.is_disconnected)

    async def event_stream() -> AsyncIterator[str]:
        async for event in events:
            yield sse_event(event)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/novel/discussion/history", response_model=list[DiscussionHistoryItemOut])
def get_discussion_history(book_name: str) -> list[dict]:
    """指定書籍のディスカッション履歴一覧を返す（B-20/B-28 両形式対応）。"""
    validate_safe_name(book_name, param_name="book_name")
    return list_discussions(book_name)


@router.delete(
    "/novel/discussion/history/{filename}",
    response_model=DiscussionDeleteOut,
)
def delete_discussion_history(filename: str, book_name: str) -> dict:
    """指定ディスカッション履歴を削除する（B-28）。"""
    validate_safe_name(book_name, param_name="book_name")
    try:
        deleted = delete_discussion(book_name, filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not deleted:
        raise HTTPException(status_code=404, detail="指定された履歴が見つかりません")
    return {"status": "deleted"}
