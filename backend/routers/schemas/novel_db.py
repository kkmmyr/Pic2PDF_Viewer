"""小説DB、検索、QA関連APIのレスポンススキーマ。"""

from typing import Literal

from pydantic import BaseModel


class BuildEnqueueResponse(BaseModel):
    job_id: int
    queued_position: int


class BuildStatusResponse(BaseModel):
    is_running: bool
    current_job: dict | None = None
    queued_jobs: list[dict]
    recent_finished: list[dict]


class DiscussionHistoryItemOut(BaseModel):
    filename: str
    created_at: str | None = None
    personas: list[dict]
    turn_count: int
    turns: list[dict]
    format_version: int = 1
    segments: list[dict] | None = None
    checks: dict | None = None


class DiscussionDeleteOut(BaseModel):
    status: str


class GraphBookOut(BaseModel):
    id: int
    name: str


class GraphDataResponse(BaseModel):
    nodes: list[dict]
    edges: list[dict]


class AmazonImportResponse(BaseModel):
    updated: int
    skipped: int
    unmatched: int


class BookSummaryOut(BaseModel):
    name: str
    authors: list[str]
    series_id: str | None
    series_title: str | None
    is_indexed: bool
    page_count: int | None
    indexed_at: str | None
    thumbnail_url: str | None
    ocr_done_at: str | None
    volume: int | None
    publisher: str | None
    asin: str | None
    series_index: float | None


class SeriesSummaryOut(BaseModel):
    id: str
    name: str
    book_count: int


class SimilarBookOut(BaseModel):
    """find_similar_books() の返却値に合わせる。"""

    name: str
    score: float


class BookDetailOut(BaseModel):
    name: str
    authors: list[str]
    series_id: str | None
    series_title: str | None
    is_indexed: bool
    page_count: int | None
    indexed_at: str | None
    thumbnail_url: str | None
    ocr_done_at: str | None
    volume: int | None
    publisher: str | None
    asin: str | None
    series_index: float | None
    isbn: str | None
    summary: str | None
    summary_generated_at: str | None
    character_count: int
    discussion_count: int


class RebuildEnqueueResponse(BaseModel):
    job_id: int
    queued_position: int


class RebuildStatusResponse(BaseModel):
    is_running: bool
    current_job: dict | None = None
    queued_jobs: list[dict]
    recent_finished: list[dict]


class SearchHitOut(BaseModel):
    book_name: str
    page_no: int
    snippet: str
    has_highlight: bool
    image_url: str | None
    rrf_score: float
    main_characters: list[str]


class SearchResponse(BaseModel):
    hits: list[SearchHitOut]
    total: int
    offset: int
    limit: int


class ScopeOut(BaseModel):
    type: Literal["all", "series", "book"]
    id: str | None


class QaHistoryItemOut(BaseModel):
    id: int
    asked_at: str
    finished_at: str | None
    scope: ScopeOut
    question: str
    answer_preview: str
    done_reason: str | None


class QaHistoryResponse(BaseModel):
    items: list[QaHistoryItemOut]
    total: int


class QaHistoryDetailResponse(BaseModel):
    id: int
    asked_at: str
    finished_at: str | None
    scope: ScopeOut
    question: str
    answer: str
    prompt: str
    context: list[SearchHitOut]
    model: str
    options: dict[str, object]
    eval_count: int | None
    done_reason: str | None
    error_message: str | None
