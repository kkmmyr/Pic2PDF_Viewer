"""小説テキスト検索・RAG（novel_db）の API ルーター。

ライブラリ表示 / 再構築ジョブ / ハイブリッド検索 / RAG 質問応答（SSE）/ 履歴。
詳細は docs/03_詳細設計/API仕様書.md §7、設計は
docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §10。
"""
from __future__ import annotations

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
    NOVEL_DB_QA_FULL_BOOK_MODE,
    NOVEL_DB_QA_FULL_BOOK_NUM_CTX,
    NOVEL_DB_QA_MAX_PER_BOOK,
    NOVEL_DB_QA_TOP_K,
    NOVEL_DB_QA_TOP_SUMMARIES,
)
from routers._deps import cancel_job_response, log_and_raise_500, sse_event
from services.novel_db import Scope, hybrid_search, with_db
from services.novel_db.character_summarizer import (
    get_character,
    list_characters,
    top_scenes_for_character,
)
from services.novel_db.job_queue import job_queue
from services.novel_db.library import get_book_detail, list_authors, list_books, list_series
from services.novel_db.llm import (
    LLM_OPTIONS,
    build_chat_context_block,
    build_chat_system_message,
    build_prompt,
    stream_chat,
    stream_qa,
)
from services.novel_db.qa_history import (
    delete_history,
    get_history_detail,
    list_history,
    save_error,
    save_finish,
    save_start,
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
from services.novel_db.query_expander import expand_query
from services.novel_db.search import SearchHit, load_all_pages_of_book, search_book_summaries
from services.novel_db.summarizer import load_summaries_for_books
from utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


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


@router.get("/novel_db/authors")
@log_and_raise_500("novel_db/authors")
def get_authors() -> list[str]:
    """novel ソースの全書籍から作者一覧（重複なし・アルファベット順）を返す（B-21）。"""
    with with_db() as conn:
        return list_authors(conn)


@router.get("/novel_db/books/{book_name:path}/detail")
@log_and_raise_500("novel_db/books/detail")
def get_book_detail_route(book_name: str) -> dict:
    """単一書籍の詳細情報（summary / character_count / discussion_count 含む）を返す。"""
    with with_db() as conn:
        detail = get_book_detail(conn, book_name)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"book not found: {book_name}")
    return asdict(detail)


# ---------------------------------------------------------------------------
# キャラクター辞典（B-15）
# ---------------------------------------------------------------------------

class CharacterSummary(BaseModel):
    """書籍内 1 キャラの一覧用ペイロード（API §7.x [characters list]）。"""
    name: str
    first_page: int
    page_count: int
    has_summary: bool


class CharacterScene(BaseModel):
    page_no: int
    char_count: int


class CharacterDetail(BaseModel):
    """書籍 × キャラの詳細（API §7.x [character detail]）。"""
    name: str
    first_page: int
    page_count: int
    summary: str | None
    generated_at: str | None
    top_scenes: list[CharacterScene]


def _resolve_book_id(conn, book_name: str) -> int:
    row = conn.execute("SELECT id FROM books WHERE name = ?", (book_name,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"book not found: {book_name}")
    return row[0]


@router.get("/novel_db/books/{book_name:path}/characters")
@log_and_raise_500("novel_db/books/characters")
def get_book_characters(book_name: str) -> list[CharacterSummary]:
    """書籍に登録済みのキャラ一覧を返す（B-15）。

    `book_characters` に未登録（CLI 未実行）の書籍は空配列。フロントは空配列なら
    「キャラ辞典 未生成」表示にフォールバックする。
    """
    with with_db() as conn:
        book_id = _resolve_book_id(conn, book_name)
        rows = list_characters(conn, book_id)
    return [
        CharacterSummary(
            name=r.name,
            first_page=r.first_page,
            page_count=r.page_count,
            has_summary=bool(r.summary and r.summary.strip()),
        )
        for r in rows
    ]


@router.get("/novel_db/books/{book_name:path}/characters/{char_name}")
@log_and_raise_500("novel_db/books/character_detail")
def get_book_character_detail(book_name: str, char_name: str) -> CharacterDetail:
    """書籍 × キャラの詳細（サマリ + 主要シーン top 5）を返す（B-15）。"""
    with with_db() as conn:
        book_id = _resolve_book_id(conn, book_name)
        row = get_character(conn, book_id, char_name)
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"character not found in '{book_name}': {char_name}",
            )
        scenes = top_scenes_for_character(conn, book_id, char_name, limit=5)
    return CharacterDetail(
        name=row.name,
        first_page=row.first_page,
        page_count=row.page_count,
        summary=row.summary,
        generated_at=row.generated_at,
        top_scenes=[
            CharacterScene(page_no=pn, char_count=cc) for pn, cc in scenes
        ],
    )


# ---------------------------------------------------------------------------
# 再構築ジョブ
# ---------------------------------------------------------------------------

class RebuildRequest(BaseModel):
    type: Literal["book", "series", "all"]
    target_id: str | None = None
    mode: Literal["rebuild", "ocr", "pdf_text", "reocr", "full_build"] = Field(default="rebuild")


@router.post("/novel_db/rebuild")
@log_and_raise_500("novel_db/rebuild")
def post_rebuild(request: RebuildRequest) -> dict:
    """再構築 / OCR ジョブをキューに登録する（[API §7.8]）。

    mode='rebuild': pages.full_text → chunk/embed を再構築（OCR 済み前提）
    mode='ocr':     images/*.png → OCR → pages.full_text を更新
    """
    if request.type in ("book", "series") and not request.target_id:
        raise HTTPException(
            status_code=422,
            detail=f"target_id is required for type='{request.type}'",
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
    return cancel_job_response(job_queue.cancel(job_id))


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


@router.post("/novel_db/qa")
async def post_qa(request: QaRequest, http_request: Request) -> StreamingResponse:
    """RAG 質問応答を SSE で返す（[API §7.4]）。"""
    _check_locked()
    scope = Scope(type=request.scope.type, id=request.scope.id)

    # B-13 段階 C（opt-in、NOVEL_DB_QA_FULL_BOOK_MODE）: scope=book のとき hybrid_search
    # を bypass して書籍全 page を読み込む。検索ノイズなしで最高品質を試すモード。
    # llama-server 側は start-qwen-server-fullbook.bat（-c 131072 / -ncmoe 32）で
    # 起動しておく必要がある。num_ctx を override する点が通常 RAG と異なる
    full_book_mode = (
        NOVEL_DB_QA_FULL_BOOK_MODE
        and scope.type == "book"
        and scope.id is not None
    )

    qa_options = LLM_OPTIONS
    if full_book_mode:
        qa_options = {**LLM_OPTIONS, "num_ctx": NOVEL_DB_QA_FULL_BOOK_NUM_CTX}

    with with_db() as conn:
        if full_book_mode:
            # Query Expansion / hybrid_search / 書籍サマリは全 page 読みなので不要
            hits = load_all_pages_of_book(
                conn,
                scope.id,
                min_chars=NOVEL_DB_MIN_BODY_CHARS,
                body_page_margin=NOVEL_DB_BODY_PAGE_MARGIN,
            )
            book_summaries = None
        else:
            # 通常 RAG 経路（段階 A/B）
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
            options=qa_options,
        )

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

@router.get("/novel_db/qa/history")
@log_and_raise_500("novel_db/qa/history")
def get_qa_history(offset: int = 0, limit: int = 20, book: str | None = None) -> dict:
    """履歴一覧（[API §7.5]）。book 指定時はその書籍の質問のみ返す。"""
    if offset < 0 or limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="invalid offset/limit")
    with with_db() as conn:
        return list_history(conn, offset=offset, limit=limit, book=book)


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


# ---------------------------------------------------------------------------
# マルチターン会話 QA（B-16）
# ---------------------------------------------------------------------------

class ChatSessionStartRequest(BaseModel):
    scope: ScopeModel
    question: str = Field(..., min_length=1, max_length=500)


class ChatSessionContinueRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


class ChatMessagePayload(BaseModel):
    id: int
    role: str
    content: str
    eval_count: int | None
    done_reason: str | None
    created_at: str


class ChatSessionSummary(BaseModel):
    id: int
    scope_type: str
    scope_id: str | None
    title: str | None
    started_at: str
    last_message_at: str | None
    message_count: int


class ChatSessionDetailPayload(BaseModel):
    id: int
    scope_type: str
    scope_id: str | None
    title: str | None
    started_at: str
    last_message_at: str | None
    messages: list[ChatMessagePayload]


def _auto_title(question: str) -> str:
    """初手質問からセッションタイトルを生成する（先頭 30 字 + 省略記号）。"""
    text = question.strip().replace("\n", " ")
    if len(text) > 30:
        return text[:30] + "…"
    return text


def _collect_initial_context(
    conn,
    scope: Scope,
    question: str,
) -> tuple[list[SearchHit], dict[str, str] | None, dict]:
    """初手の context（hits + book_summaries + LLM options）を組み立てる。

    既存 `/qa` の hits 構築ロジックと同等。`scope=book` のとき
    `NOVEL_DB_QA_FULL_BOOK_MODE` なら全 page 読み、それ以外はハイブリッド検索。
    `book_summaries` は scope=all / series のみ付与する。
    """
    full_book_mode = (
        NOVEL_DB_QA_FULL_BOOK_MODE and scope.type == "book" and scope.id is not None
    )
    qa_options = LLM_OPTIONS
    if full_book_mode:
        qa_options = {**LLM_OPTIONS, "num_ctx": NOVEL_DB_QA_FULL_BOOK_NUM_CTX}

    if full_book_mode:
        hits = load_all_pages_of_book(
            conn, scope.id,
            min_chars=NOVEL_DB_MIN_BODY_CHARS,
            body_page_margin=NOVEL_DB_BODY_PAGE_MARGIN,
        )
        return hits, None, qa_options

    max_per_book = (
        NOVEL_DB_QA_MAX_PER_BOOK if scope.type in ("all", "series") else None
    )
    queries = expand_query(question) if NOVEL_DB_QA_EXPAND_ENABLED else [question]

    rows_by_key: dict[tuple[str, int], SearchHit] = {}
    for q in queries:
        sub_rows = hybrid_search(
            conn, q, scope,
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

    if scope.type in ("all", "series"):
        hit_book_names = {h.book_name for h in hits}
        summary_hits = search_book_summaries(
            conn, question, scope, top=NOVEL_DB_QA_TOP_SUMMARIES,
        )
        relevant_book_names = sorted(
            hit_book_names | {name for name, _ in summary_hits},
        )
        book_summaries = load_summaries_for_books(conn, relevant_book_names)
    else:
        book_summaries = None
    return hits, book_summaries, qa_options


@router.get("/novel_db/qa/sessions")
@log_and_raise_500("novel_db/qa/sessions")
def get_chat_sessions(offset: int = 0, limit: int = 20) -> list[ChatSessionSummary]:
    """会話セッション一覧（B-16）。"""
    if offset < 0 or limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="invalid offset/limit")
    with with_db() as conn:
        rows = list_sessions(conn, offset=offset, limit=limit)
    return [
        ChatSessionSummary(
            id=r.id, scope_type=r.scope_type, scope_id=r.scope_id,
            title=r.title, started_at=r.started_at,
            last_message_at=r.last_message_at, message_count=r.message_count,
        )
        for r in rows
    ]


@router.get("/novel_db/qa/sessions/{session_id}")
@log_and_raise_500("novel_db/qa/sessions/detail")
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


@router.delete("/novel_db/qa/sessions/{session_id}", status_code=204)
@log_and_raise_500("novel_db/qa/sessions/delete")
def delete_chat_session(session_id: int) -> Response:
    """会話セッション削除（メッセージは CASCADE で連動削除）（B-16）。"""
    with with_db() as conn:
        ok = delete_session(conn, session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    return Response(status_code=204)


@router.post("/novel_db/qa/sessions")
async def post_chat_session_start(
    request: ChatSessionStartRequest,
    http_request: Request,
) -> StreamingResponse:
    """会話セッション開始 + 初手 SSE（B-16）。

    1. session 作成 + system / user メッセージを DB に append
    2. stream_chat に [system, user] を投入し、token を SSE で配信
    3. 終端で assistant メッセージを DB に append
    """
    _check_locked()
    scope = Scope(type=request.scope.type, id=request.scope.id)

    with with_db() as conn:
        hits, book_summaries, qa_options = _collect_initial_context(
            conn, scope, request.question,
        )
        context_block = build_chat_context_block(
            hits, scope, book_summaries=book_summaries,
        )
        system_message = build_chat_system_message(
            scope, context_block=context_block,
        )
        session_id = create_session(conn, scope, title=_auto_title(request.question))
        append_message(conn, session_id, role="system", content=system_message)
        append_message(conn, session_id, role="user", content=request.question)

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": request.question},
    ]
    return StreamingResponse(
        _chat_event_stream(http_request, session_id, messages, qa_options),
        media_type="text/event-stream",
    )


@router.post("/novel_db/qa/sessions/{session_id}/messages")
async def post_chat_session_message(
    session_id: int,
    request: ChatSessionContinueRequest,
    http_request: Request,
) -> StreamingResponse:
    """会話セッションへの追加ターン SSE（B-16）。

    1. 既存 messages（system + user/assistant 履歴）を取得
    2. 新規 user メッセージを DB に append
    3. messages + new user を投入し SSE で配信
    4. 終端で assistant メッセージを DB に append
    """
    _check_locked()
    with with_db() as conn:
        detail = get_session_detail(conn, session_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="session not found")
        prior = load_chat_messages(conn, session_id)
        append_message(conn, session_id, role="user", content=request.question)

    messages = prior + [{"role": "user", "content": request.question}]
    # 続行ターンは初手と同じ qa_options を使う（scope 固定なので場合分け不要）
    qa_options = LLM_OPTIONS
    if detail.scope_type == "book" and NOVEL_DB_QA_FULL_BOOK_MODE:
        qa_options = {**LLM_OPTIONS, "num_ctx": NOVEL_DB_QA_FULL_BOOK_NUM_CTX}
    return StreamingResponse(
        _chat_event_stream(http_request, session_id, messages, qa_options),
        media_type="text/event-stream",
    )


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
        # Ollama 経路など chat 非対応のバックエンドで起きる。500 相当のエラーを SSE で返す。
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


# title 更新 (任意、UX 改善)
@router.patch("/novel_db/qa/sessions/{session_id}/title")
@log_and_raise_500("novel_db/qa/sessions/title")
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

