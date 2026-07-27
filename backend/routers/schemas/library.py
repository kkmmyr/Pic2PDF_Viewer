"""ライブラリ、生成、メタデータ関連APIのレスポンススキーマ。"""

from typing import Literal

from pydantic import BaseModel


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


class GenreListResponse(BaseModel):
    genres: list[str]


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


class PrefsResponse(BaseModel):
    read_state_filter: str
    genre_filter: str
    series_pins: dict[str, str]
    author_pins: dict[str, str]


class PrefsUpdateResponse(BaseModel):
    message: str


class BookMetaEntryOut(BaseModel):
    """meta2.db の書籍メタデータ 1 件。"""

    authors: list[str]
    view_count: int | None = None
    last_viewed_at: float | None = None
    hidden: bool | None = None
    genre: str | None = None
    read_state: Literal["unread", "reading", "done"] | None = None
    series_id: str | None = None
    series_title: str | None = None
    series_index: float | None = None
    volume: int | None = None
    publisher: str | None = None
    asin: str | None = None
    isbn: str | None = None
    release_date: str | None = None


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
    reason: str


class SeriesSuggestResponse(BaseModel):
    candidates: list[SuggestedSeriesOut]


class RegenerateThumbnailResponse(BaseModel):
    message: str


class RegenerateThumbnailBulkResponse(BaseModel):
    message: str
    succeeded: list[str]
    failed: list[str]


class AdminInitResponse(BaseModel):
    updated: int
    inserted: int


class MetaUpdateResponse(BaseModel):
    message: str
    updated_count: int


class RecordViewResponse(BaseModel):
    view_count: int
    last_viewed_at: float
    incremented: bool
    read_state: str | None = None


class NovelMetaUpdateResponse(BaseModel):
    message: str
