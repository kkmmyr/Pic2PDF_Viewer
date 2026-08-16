"""小説DB、検索、QA関連APIのレスポンススキーマ。"""

from typing import Literal

from pydantic import BaseModel

RebuildJobType = Literal["book", "series", "all"]
RebuildJobMode = Literal[
    "rebuild",
    "ocr",
    "full_build",
    "generate_contexts",
    "generate_relations",
]
BuildJobMode = Literal["full_build", "generate_contexts", "generate_relations"]
FinishedJobState = Literal["completed", "failed", "canceled"]


class BuildEnqueueResponse(BaseModel):
    job_id: int
    queued_position: int


class BuildRunningJobOut(BaseModel):
    id: int
    target_id: str | None
    mode: BuildJobMode
    started_at: str | None = None
    progress_total: int | None = None
    progress_done: int | None = None
    current_step: str | None = None
    current_detail: str | None = None


class BuildQueuedJobOut(BaseModel):
    id: int
    target_id: str | None
    mode: BuildJobMode
    enqueued_at: str | None = None


class BuildFinishedJobOut(BaseModel):
    id: int
    target_id: str | None
    mode: BuildJobMode
    state: FinishedJobState
    finished_at: str | None = None
    error_message: str | None = None


class BuildStatusResponse(BaseModel):
    is_running: bool
    current_job: BuildRunningJobOut | None = None
    queued_jobs: list[BuildQueuedJobOut]
    recent_finished: list[BuildFinishedJobOut]


class DiscussionPersonaOut(BaseModel):
    name: str
    style_description: str


class DiscussionTurnOut(BaseModel):
    speaker: str
    text: str
    segment: str | None = None


class DiscussionSegmentOut(BaseModel):
    id: str
    title: str


class DiscussionCheckResultOut(BaseModel):
    id: str
    label: str
    passed: bool
    detail: str


class DiscussionChecksOut(BaseModel):
    passed: bool
    results: list[DiscussionCheckResultOut]


class DiscussionHistoryItemOut(BaseModel):
    filename: str
    created_at: str | None = None
    personas: list[DiscussionPersonaOut]
    turn_count: int
    turns: list[DiscussionTurnOut]
    format_version: Literal[1, 2] = 1
    segments: list[DiscussionSegmentOut] | None = None
    checks: DiscussionChecksOut | None = None


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
    catalog_summary: str | None = None
    catalog_summary_generated_at: str | None = None
    read_state: Literal["unread", "reading", "done"]


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
    catalog_summary: str | None = None
    catalog_summary_generated_at: str | None = None
    character_count: int
    discussion_count: int
    read_state: Literal["unread", "reading", "done"]


class RebuildEnqueueResponse(BaseModel):
    job_id: int
    queued_position: int


class RebuildRunningJobOut(BaseModel):
    id: int
    type: RebuildJobType
    target_id: str | None
    mode: RebuildJobMode
    started_at: str | None = None
    progress_total: int | None = None
    progress_done: int | None = None
    current_step: str | None = None
    current_detail: str | None = None


class RebuildQueuedJobOut(BaseModel):
    id: int
    type: RebuildJobType
    target_id: str | None
    mode: RebuildJobMode
    enqueued_at: str | None = None


class RebuildFinishedJobOut(BaseModel):
    id: int
    type: RebuildJobType
    target_id: str | None
    mode: RebuildJobMode
    state: FinishedJobState
    finished_at: str | None = None
    error_message: str | None = None


class RebuildStatusResponse(BaseModel):
    is_running: bool
    current_job: RebuildRunningJobOut | None = None
    queued_jobs: list[RebuildQueuedJobOut]
    recent_finished: list[RebuildFinishedJobOut]


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
