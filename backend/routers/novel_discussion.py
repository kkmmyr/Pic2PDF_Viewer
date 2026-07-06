"""B-28 読書会ロングフォーム生成 API ルーター（B-20 を置き換え）。

POST   /api/novel/discussion/generate             → SSE ストリーミング（構成→台本の 2 段生成）
GET    /api/novel/discussion/history              → 過去生成一覧（?book_name=<name>）
DELETE /api/novel/discussion/history/{filename}   → 履歴削除（?book_name=<name>）
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import NOVEL_DB_BODY_PAGE_MARGIN, NOVEL_DB_MIN_BODY_CHARS
from routers._deps import sse_event
from routers.api_schemas import DiscussionDeleteOut, DiscussionHistoryItemOut
from services.novel_db.connection import with_db
from services.novel_db.discussion_cast import HOST_A, HOST_B
from services.novel_db.discussion_checks import run_checks
from services.novel_db.discussion_prompts import (
    build_plan_messages,
    build_script_messages,
    resolve_segment_titles,
)
from services.novel_db.discussion_service import (
    MAX_INPUT_TOKENS,
    delete_discussion,
    estimate_book_tokens,
    format_book_text,
    generate_plan,
    list_discussions,
    save_discussion,
    stream_discussion_turns,
)
from services.novel_db.search import load_all_pages_of_book
from utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


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
    with with_db() as conn:
        hits = load_all_pages_of_book(
            conn,
            request.book_name,
            min_chars=NOVEL_DB_MIN_BODY_CHARS,
            body_page_margin=NOVEL_DB_BODY_PAGE_MARGIN,
        )

    if not hits:

        async def _no_pages() -> AsyncGenerator[str, None]:
            yield sse_event(
                {
                    "type": "error",
                    "message": f"書籍「{request.book_name}」のページデータが見つかりません。インデックスを再構築してください。",
                }
            )

        return StreamingResponse(_no_pages(), media_type="text/event-stream")

    token_count = estimate_book_tokens(hits)
    if token_count > MAX_INPUT_TOKENS:

        async def _too_long() -> AsyncGenerator[str, None]:
            yield sse_event(
                {
                    "type": "error",
                    "message": (
                        f"本文が長すぎます（推定 {token_count:,} トークン、上限 {MAX_INPUT_TOKENS:,} トークン）。"
                    ),
                }
            )

        return StreamingResponse(_too_long(), media_type="text/event-stream")

    book_text = format_book_text(hits)

    async def event_stream() -> AsyncGenerator[str, None]:
        # --- 構成ステップ（Call 1） ---
        yield sse_event({"type": "status", "stage": "planning"})
        try:
            plan = await generate_plan(build_plan_messages(request.book_name, book_text))
        except Exception as e:
            logger.exception("generate_discussion planning failed")
            yield sse_event({"type": "error", "message": str(e)})
            return

        segments = resolve_segment_titles(plan)
        segment_titles = {s["id"]: s["title"] for s in segments}

        # --- 台本ステップ（Call 2） ---
        yield sse_event({"type": "status", "stage": "scripting"})
        script_messages = build_script_messages(request.book_name, book_text, plan)
        accumulated_turns: list[dict] = []
        segments_seen: list[str] = []
        try:
            async for ev in stream_discussion_turns(script_messages):
                if await http_request.is_disconnected():
                    return
                if ev["type"] == "segment":
                    segments_seen.append(ev["id"])
                    yield sse_event(
                        {
                            "type": "segment",
                            "id": ev["id"],
                            "title": segment_titles.get(ev["id"], ev["id"]),
                        }
                    )
                    continue
                accumulated_turns.append(
                    {
                        "speaker": ev["speaker"],
                        "text": ev["text"],
                        "segment": ev["segment"],
                    }
                )
                yield sse_event(ev)
        except Exception as e:
            logger.exception("generate_discussion SSE failed")
            yield sse_event({"type": "error", "message": str(e)})
            return

        if not accumulated_turns:
            yield sse_event({"type": "done"})
            return

        checks = run_checks(accumulated_turns, segments_seen, plan["cards"])
        cast_snapshot = [
            {
                "id": HOST_A.id,
                "marker": HOST_A.marker,
                "name": HOST_A.name,
                "profile": HOST_A.profile,
                "stance": plan["stances"]["a"],
            },
            {
                "id": HOST_B.id,
                "marker": HOST_B.marker,
                "name": HOST_B.name,
                "profile": HOST_B.profile,
                "stance": plan["stances"]["b"],
            },
        ]
        saved_path = save_discussion(
            request.book_name,
            cast_snapshot,
            segments,
            plan["cards"],
            accumulated_turns,
            checks,
        )
        yield sse_event({"type": "done", "saved_path": saved_path, "checks": checks})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/novel/discussion/history", response_model=list[DiscussionHistoryItemOut])
def get_discussion_history(book_name: str) -> list[dict]:
    """指定書籍のディスカッション履歴一覧を返す（B-20/B-28 両形式対応）。"""
    return list_discussions(book_name)


@router.delete(
    "/novel/discussion/history/{filename}",
    response_model=DiscussionDeleteOut,
)
def delete_discussion_history(filename: str, book_name: str) -> dict:
    """指定ディスカッション履歴を削除する（B-28）。"""
    try:
        deleted = delete_discussion(book_name, filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not deleted:
        raise HTTPException(status_code=404, detail="指定された履歴が見つかりません")
    return {"status": "deleted"}
