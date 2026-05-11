"""小説テキスト検索・RAG（novel_db）の API ルーター。

ライブラリ表示 / 再構築ジョブ / ハイブリッド検索 / RAG 質問応答（SSE）/ 履歴。
詳細は docs/03_詳細設計/API仕様書.md §7、設計は
docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §10。
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import (
    NOVEL_DB_BODY_PAGE_MARGIN,
    NOVEL_DB_LLM_MODEL,
    NOVEL_DB_MIN_BODY_CHARS,
    NOVEL_DB_QA_EXPAND_ENABLED,
    NOVEL_DB_QA_MAX_PER_BOOK,
    NOVEL_DB_QA_TOP_K,
    NOVEL_DB_QA_TOP_SUMMARIES,
)
from routers._deps import log_and_raise_500
from services.novel_db import Scope, hybrid_search, with_db
from services.novel_db.job_queue import job_queue
from services.novel_db.library import list_books, list_series
from services.novel_db.llm import LLM_OPTIONS, build_prompt, stream_qa
from services.novel_db.qa_history import (
    delete_history,
    get_history_detail,
    list_history,
    save_error,
    save_finish,
    save_start,
)
from services.novel_db.query_expander import expand_query
from services.novel_db.search import SearchHit, search_book_summaries
from services.novel_db.summarizer import load_summaries_for_books

router = APIRouter()


def _check_locked() -> None:
    """再構築ジョブ実行中なら 503 を返す共通チェック。"""
    if job_queue.is_running:
        raise HTTPException(
            status_code=503,
            detail="rebuild is in progress",
            headers={"Retry-After": "10"},
        )


# ---------------------------------------------------------------------------
# ライブラリ
# ---------------------------------------------------------------------------

@router.get("/novel_db/books")
@log_and_raise_500("novel_db/books")
def get_books() -> list[dict]:
    """書籍一覧 + DB 状態を返す（[API §7.1]）。"""
    with with_db() as conn:
        return [asdict(b) for b in list_books(conn)]


@router.get("/novel_db/series")
@log_and_raise_500("novel_db/series")
def get_series() -> list[dict]:
    """novel ソースのシリーズ一覧（書籍 1 件以上のみ）（[API §7.2]）。"""
    with with_db() as conn:
        return [asdict(s) for s in list_series(conn)]


# ---------------------------------------------------------------------------
# 再構築ジョブ
# ---------------------------------------------------------------------------

class RebuildRequest(BaseModel):
    type: Literal["book", "series", "all"]
    target_id: str | None = None
    mode: Literal["pdf_text", "reocr"] = Field(default="pdf_text")


@router.post("/novel_db/rebuild")
@log_and_raise_500("novel_db/rebuild")
def post_rebuild(request: RebuildRequest) -> dict:
    """再構築ジョブをキューに登録する（[API §7.8]）。"""
    if request.type in ("book", "series") and not request.target_id:
        raise HTTPException(
            status_code=422,
            detail=f"target_id is required for type='{request.type}'",
        )
    if request.mode == "reocr":
        raise HTTPException(
            status_code=422,
            detail="mode='reocr' is not implemented yet (planned in a future phase)",
        )

    job_id, queued_position = job_queue.enqueue(
        request.type, request.target_id, request.mode
    )
    return {"job_id": job_id, "queued_position": queued_position}


@router.get("/novel_db/rebuild/status")
@log_and_raise_500("novel_db/rebuild/status")
def get_rebuild_status() -> dict:
    """現在のキュー状態を返す（[API §7.9]）。"""
    return job_queue.get_status()


@router.delete("/novel_db/rebuild/{job_id}", status_code=204)
@log_and_raise_500("novel_db/rebuild/cancel")
def delete_rebuild(job_id: int) -> Response:
    """待機中ジョブをキャンセルする（[API §7.10]）。実行中は 409。"""
    result = job_queue.cancel(job_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="job not found")
    if result == "running":
        raise HTTPException(
            status_code=409, detail="cannot cancel a running job"
        )
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# 検索 (FTS5 + ベクトル + RRF)
# ---------------------------------------------------------------------------

class ScopeModel(BaseModel):
    type: Literal["all", "series", "book"]
    id: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    scope: ScopeModel
    offset: int = Field(0, ge=0)
    limit: int = Field(20, ge=1, le=50)


@router.post("/novel_db/search")
@log_and_raise_500("novel_db/search")
def post_search(request: SearchRequest) -> dict:
    """ハイブリッド検索（[API §7.3]）。

    `min_chars` でノイズページ（章扉・目次・人物紹介・あとがき等）を除外する。
    検索 API では書籍偏りを許容（max_per_book は適用しない）。
    """
    _check_locked()
    scope = Scope(type=request.scope.type, id=request.scope.id)
    end = request.offset + request.limit
    with with_db() as conn:
        all_hits = hybrid_search(
            conn,
            request.query,
            scope,
            top=end,
            min_chars=NOVEL_DB_MIN_BODY_CHARS,
            body_page_margin=NOVEL_DB_BODY_PAGE_MARGIN,
        )
    page = all_hits[request.offset : end]
    return {
        "hits": [asdict(h) for h in page],
        "total": len(all_hits),
        "offset": request.offset,
        "limit": request.limit,
    }


# ---------------------------------------------------------------------------
# 質問応答 (SSE)
# ---------------------------------------------------------------------------

class QaRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    scope: ScopeModel


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/novel_db/qa")
async def post_qa(request: QaRequest, http_request: Request) -> StreamingResponse:
    """RAG 質問応答を SSE で返す（[API §7.4]）。"""
    _check_locked()
    scope = Scope(type=request.scope.type, id=request.scope.id)

    # 検索 + 履歴の準備（同期処理、SSE 開始前に完了させる）
    # scope=all / series では書籍偏り抑制のため max_per_book を有効化、
    # 単冊（book）スコープでは不要なので None。
    max_per_book = (
        NOVEL_DB_QA_MAX_PER_BOOK if scope.type in ("all", "series") else None
    )

    # B-11 Query Expansion: 元の質問 + 展開クエリで multi-query 検索する。
    # 展開無効時 / 失敗時は元の質問のみのリストが返るので、結果は従来と同じになる。
    if NOVEL_DB_QA_EXPAND_ENABLED:
        queries = expand_query(request.question)
    else:
        queries = [request.question]

    with with_db() as conn:
        # 各クエリで hybrid_search → (book_name, page_no) でデデュープし、
        # 同じページが複数クエリから引かれた場合はスコア最大値を採用する
        rows_by_key: dict[tuple[str, int], SearchHit] = {}
        for q in queries:
            sub_rows = hybrid_search(
                conn,
                q,
                scope,
                top=NOVEL_DB_QA_TOP_K,
                min_chars=NOVEL_DB_MIN_BODY_CHARS,
                max_per_book=max_per_book,
                body_page_margin=NOVEL_DB_BODY_PAGE_MARGIN,
            )
            for h in sub_rows:
                key = (h.book_name, h.page_no)
                existing = rows_by_key.get(key)
                if existing is None or h.rrf_score > existing.rrf_score:
                    rows_by_key[key] = h
        hits = sorted(rows_by_key.values(), key=lambda h: -h.rrf_score)[
            :NOVEL_DB_QA_TOP_K
        ]
        # scope=all / series ではヒット書籍の俯瞰サマリをプロンプトに付与する
        # （生成済み書籍のみ。未生成は単に含めない＝後方互換）
        # B-8: ページヒット書籍に加えて、サマリ自体のベクトル検索 top-K も合流
        # させ、ページに引っかからなかった書籍も俯瞰サマリとしてプロンプトに乗せる
        if scope.type in ("all", "series"):
            hit_book_names = {h.book_name for h in hits}
            summary_hits = search_book_summaries(
                conn, request.question, scope, top=NOVEL_DB_QA_TOP_SUMMARIES,
            )
            relevant_book_names = sorted(
                hit_book_names | {name for name, _ in summary_hits},
            )
            book_summaries = load_summaries_for_books(conn, relevant_book_names)
        else:
            book_summaries = None
        prompt = build_prompt(
            request.question, hits, scope, book_summaries=book_summaries,
        )
        history_id = save_start(
            conn,
            scope=scope,
            question=request.question,
            prompt=prompt,
            hits=hits,
            model=NOVEL_DB_LLM_MODEL,
            options=LLM_OPTIONS,
        )

    async def event_stream():
        full_response: list[str] = []
        try:
            async for event in stream_qa(prompt):
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
                    yield _sse_event({"token": event["response"]})
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
                    yield _sse_event({
                        "done": True,
                        "history_id": history_id,
                        "eval_count": eval_count,
                        "done_reason": done_reason,
                    })
                    return
        except Exception as e:
            with with_db() as conn:
                save_error(conn, history_id, str(e))
            yield _sse_event({"error": str(e)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# 履歴
# ---------------------------------------------------------------------------

@router.get("/novel_db/qa/history")
@log_and_raise_500("novel_db/qa/history")
def get_qa_history(offset: int = 0, limit: int = 20) -> dict:
    """履歴一覧（[API §7.5]）。"""
    if offset < 0 or limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="invalid offset/limit")
    with with_db() as conn:
        return list_history(conn, offset=offset, limit=limit)


@router.get("/novel_db/qa/history/{history_id}")
@log_and_raise_500("novel_db/qa/history/detail")
def get_qa_history_detail(history_id: int) -> dict:
    """履歴詳細（[API §7.6]）。"""
    with with_db() as conn:
        detail = get_history_detail(conn, history_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="history not found")
    return detail


@router.delete("/novel_db/qa/history/{history_id}", status_code=204)
@log_and_raise_500("novel_db/qa/history/delete")
def delete_qa_history(history_id: int) -> Response:
    """履歴削除（[API §7.7]）。"""
    with with_db() as conn:
        ok = delete_history(conn, history_id)
    if not ok:
        raise HTTPException(status_code=404, detail="history not found")
    return Response(status_code=204)
