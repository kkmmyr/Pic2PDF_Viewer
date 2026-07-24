"""FastAPI response_model 定義。

openapi-typescript による TypeScript 型自動生成のために、
各エンドポイントの実際の返却値と一致する Pydantic モデルを定義する。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# library.py 用
# ---------------------------------------------------------------------------


class PdfFileOut(BaseModel):
    name: str
    thumbnail: str | None = None
    created_at: int


class PdfListResponse(BaseModel):
    files: list[PdfFileOut]
    current_path: str


class BookImagesResponse(BaseModel):
    images: list[str]


class RenameResponse(BaseModel):
    message: str
    new_name: str


class DeleteResponse(BaseModel):
    message: str
    deleted_count: int
    errors: list[str]


# ---------------------------------------------------------------------------
# generate.py 用
# ---------------------------------------------------------------------------


class GenerateJobOut(BaseModel):
    """GenerateJob.to_dict() の返却値に合わせる。"""

    job_id: str
    status: str
    current_item: str | None = None
    files: list[str]
    failed_items: list[dict]
    message: str
    error: str | None = None
    trigger: str = "manual"


class GenerateStartResponse(BaseModel):
    """POST /generate の返却値。"""

    job_id: str
    status: str


# ---------------------------------------------------------------------------
# generate.py 用 — 同人誌フォルダ自動監視ステータス
# ---------------------------------------------------------------------------


class GenerateWatcherPendingItemOut(BaseModel):
    name: str
    kind: str


class GenerateWatcherLastAutoJobOut(BaseModel):
    job_id: str
    status: str
    finished_at: str


class GenerateWatcherResponse(BaseModel):
    """GET /generate/watcher の返却値。"""

    enabled: bool
    state: str
    interval_sec: int
    last_scan_at: str | None = None
    pending_items: list[GenerateWatcherPendingItemOut]
    active_job_id: str | None = None
    last_auto_job: GenerateWatcherLastAutoJobOut | None = None
    retry_blocked: bool


# ---------------------------------------------------------------------------
# genres.py 用
# ---------------------------------------------------------------------------


class GenreListResponse(BaseModel):
    genres: list[str]


# ---------------------------------------------------------------------------
# hitomi.py 用
# ---------------------------------------------------------------------------


class HitomiArrivalItem(BaseModel):
    id: int
    artist: str
    display_artist: str
    title: str
    language: str
    type: str
    page_count: int
    published_at: str | None = None
    discovered_at: str
    url: str
    is_read: bool
    read_at: str | None = None


class HitomiArrivalsResponse(BaseModel):
    items: list[HitomiArrivalItem]
    status: Literal["unread", "read", "all"]
    total: int
    unread_count: int
    read_count: int
    offset: int
    limit: int
    last_run_at: str | None = None
    last_run_status: Literal["ok", "partial", "error", "never"]
    last_error: str | None = None


class HitomiDismissResponse(BaseModel):
    message: str
    id: int


class HitomiDismissAllResponse(BaseModel):
    message: str
    dismissed_count: int


class HitomiWatchlistEntry(BaseModel):
    display_name: str
    normalized: str
    language: str
    added_at: str = ""


class HitomiWatchlistResponse(BaseModel):
    artists: list[HitomiWatchlistEntry]


class HitomiAddArtistResponse(BaseModel):
    message: str
    normalized: str


class HitomiRemoveArtistResponse(BaseModel):
    message: str


class HitomiRunStats(BaseModel):
    added: int
    skipped: int
    errors: int


class HitomiRunNowResponse(BaseModel):
    exit_code: int
    last_run_at: str | None = None
    last_run_status: Literal["ok", "partial", "error", "never"]
    last_error: str | None = None
    last_run_stats: HitomiRunStats | None = None


# ---------------------------------------------------------------------------
# meta_db_backup.py 用
# ---------------------------------------------------------------------------


class BackupTriggeredResponse(BaseModel):
    path: str
    size_bytes: int
    backed_up_at: str


class BackupStatusResponse(BaseModel):
    last_backup: dict | None = None
    backup_dir: str | None = None
    total_backups: int


# ---------------------------------------------------------------------------
# novel_build.py 用
# ---------------------------------------------------------------------------


class BuildEnqueueResponse(BaseModel):
    job_id: int
    queued_position: int


class BuildStatusResponse(BaseModel):
    is_running: bool
    current_job: dict | None = None
    queued_jobs: list[dict]
    recent_finished: list[dict]


# ---------------------------------------------------------------------------
# novel_discussion.py 用
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# novel_graph.py 用
# ---------------------------------------------------------------------------


class GraphBookOut(BaseModel):
    id: int
    name: str


class GraphDataResponse(BaseModel):
    nodes: list[dict]
    edges: list[dict]


# ---------------------------------------------------------------------------
# pdfs.py 用
# ---------------------------------------------------------------------------


class DeletePagesResponse(BaseModel):
    message: str
    total_pages: int


class ReorderPagesResponse(BaseModel):
    message: str
    total_pages: int


class MergePdfsResponse(BaseModel):
    message: str
    output_name: str
    total_pages: int


# ---------------------------------------------------------------------------
# prefs.py 用
# ---------------------------------------------------------------------------


class PrefsResponse(BaseModel):
    read_state_filter: str
    genre_filter: str
    series_pins: dict[str, str]
    author_pins: dict[str, str]


class PrefsUpdateResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# series.py 用
# ---------------------------------------------------------------------------


class SeriesAssignResponse(BaseModel):
    message: str
    id: str
    updated_count: int


class SeriesUnassignResponse(BaseModel):
    message: str
    updated_count: int


class SeriesReorderResponse(BaseModel):
    message: str
    updated_count: int


class SuggestedSeriesOut(BaseModel):
    series_id: str
    series_title: str
    series_max_index: float
    score: float
    reason: str  # カンマ区切り文字列 ("title_match,author_match")


class SeriesSuggestResponse(BaseModel):
    candidates: list[SuggestedSeriesOut]


# ---------------------------------------------------------------------------
# thumbnails.py 用
# ---------------------------------------------------------------------------


class RegenerateThumbnailResponse(BaseModel):
    message: str


class RegenerateThumbnailBulkResponse(BaseModel):
    message: str
    succeeded: list[str]
    failed: list[str]


# ---------------------------------------------------------------------------
# meta/admin.py 用
# ---------------------------------------------------------------------------


class AdminInitResponse(BaseModel):
    updated: int
    inserted: int


# ---------------------------------------------------------------------------
# meta/core.py 用
# ---------------------------------------------------------------------------


class MetaUpdateResponse(BaseModel):
    message: str
    updated_count: int


class RecordViewResponse(BaseModel):
    view_count: int
    last_viewed_at: float
    incremented: bool
    read_state: str | None = None


# ---------------------------------------------------------------------------
# meta/novel.py 用
# ---------------------------------------------------------------------------


class NovelMetaUpdateResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# amazon_import.py 用
# ---------------------------------------------------------------------------


class AmazonImportResponse(BaseModel):
    updated: int
    skipped: int
    unmatched: int


# ---------------------------------------------------------------------------
# novel_db/lib.py 用
# ※ BookSummary / BookDetail は services/novel_db/library.py のフィールドに合わせる
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# novel_db/rebuild.py 用
# ---------------------------------------------------------------------------


class RebuildEnqueueResponse(BaseModel):
    job_id: int
    queued_position: int


class RebuildStatusResponse(BaseModel):
    is_running: bool
    current_job: dict | None = None
    queued_jobs: list[dict]
    recent_finished: list[dict]


# ---------------------------------------------------------------------------
# novel_db/search.py 用
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# novel_db/qa.py 用
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# ocr.py 用
# ---------------------------------------------------------------------------


class OcrRunResponse(BaseModel):
    status: str
    job_id: int
    queue_position: int


class OcrStopResponse(BaseModel):
    status: str
    canceled_jobs: list[int]
