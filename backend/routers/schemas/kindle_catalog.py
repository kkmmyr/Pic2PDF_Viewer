"""Kindle購入カタログと自動撮影APIのスキーマ。"""

from typing import Literal

from pydantic import BaseModel


class MigrationCommitRequest(BaseModel):
    confirmation_token: str


class LinkRequest(BaseModel):
    source: Literal["comic", "novel"]
    book_id: str
    asin: str


class UnlinkRequest(BaseModel):
    source: Literal["comic", "novel"]
    book_id: str


class CaptureJobCreateRequest(BaseModel):
    asin: str
    source: Literal["comic", "novel"]
    direction: Literal["left", "right"] = "left"
    expected_screens: int | None = None


class AgentClaimRequest(BaseModel):
    agent_id: str


class AgentStateRequest(BaseModel):
    agent_id: str
    state: Literal[
        "locating_book",
        "downloading",
        "positioning",
        "waiting_user",
        "capturing",
        "awaiting_files",
        "failed",
    ]
    captured_screens: int | None = None
    error_code: str | None = None
    error_message: str | None = None


class AgentCompleteRequest(BaseModel):
    agent_id: str


class AgentHeartbeatRequest(BaseModel):
    agent_id: str


class KindleCatalogBookOut(BaseModel):
    asin: str
    title: str
    authors: list[str]
    genres: list[str]
    publisher: str | None
    book_type: str
    kindle_acquisition_date: str | None
    is_completed: bool | None
    ownership: Literal["purchased", "borrowed_active", "borrowed_ended", "returned", "unknown"]
    capture_state: Literal["not_captured", "captured", "multiple_links", "capture_pending"]
    series_id: int | None
    series_name: str | None
    volume_number: float | None
    volume_label: str | None


class KindleCatalogBooksResponse(BaseModel):
    items: list[KindleCatalogBookOut]
    total: int
    page: int
    page_size: int


class KindleImportRunOut(BaseModel):
    id: int
    source_kind: str
    status: str
    started_at: str
    finished_at: str | None
    files_processed: int
    records_processed: int
    records_skipped: int
    error_message: str | None


class KindleCatalogStatsResponse(BaseModel):
    books: int
    purchases: int
    borrowings: int
    returns: int
    series: int
    captured: int
    last_import: KindleImportRunOut | None


class KindleCatalogSourceStatusResponse(BaseModel):
    legacy_db_configured: bool
    legacy_db_available: bool
    legacy_db_name: str | None
    amazon_data_configured: bool


class KindleMigrationPreviewResponse(BaseModel):
    configured: bool
    source_name: str
    source_size: int
    fingerprint: str
    integrity: str
    counts: dict[str, int]
    excluded_counts: dict[str, int]
    missing_asin: int
    confirmation_token: str
    expires_at: str
    images_migrated: bool


class KindleMigrationCommitResponse(BaseModel):
    run_id: int
    status: str
    records_processed: int
    records_skipped: int
    images_migrated: bool


class KindleImportRunsResponse(BaseModel):
    items: list[KindleImportRunOut]


class KindleUnlinkedBookOut(BaseModel):
    source: Literal["comic", "novel"]
    book_id: str
    title: str
    authors: list[str]
    series_title: str | None


class KindleUnlinkedBooksResponse(BaseModel):
    items: list[KindleUnlinkedBookOut]


class KindleLinkCandidateOut(BaseModel):
    asin: str
    title: str
    authors: list[str]
    book_type: str
    score: int
    reasons: list[str]


class KindleLinkCandidatesResponse(BaseModel):
    items: list[KindleLinkCandidateOut]


class KindleLinkResponse(BaseModel):
    source: Literal["comic", "novel"]
    book_id: str
    asin: str


class KindleUnlinkResponse(BaseModel):
    source: Literal["comic", "novel"]
    book_id: str
    unlinked: bool


class KindleImportFileResultOut(BaseModel):
    filename: str
    kind: str
    status: str
    records: int


class KindleOrdersImportResponse(BaseModel):
    run_id: int
    status: str
    files_processed: int
    files_skipped: int
    records_processed: int
    records_skipped: int = 0
    files: list[KindleImportFileResultOut]


class KindleCaptureJobOut(BaseModel):
    id: str
    asin: str
    source: Literal["comic", "novel"]
    status: str
    direction: Literal["left", "right"]
    expected_screens: int | None
    requested_at: str
    claimed_at: str | None
    heartbeat_at: str | None
    started_at: str | None
    completed_at: str | None
    agent_id: str | None
    book_id: str | None
    captured_screens: int | None
    error_code: str | None
    error_message: str | None
    title: str | None = None


class KindleCaptureJobsResponse(BaseModel):
    items: list[KindleCaptureJobOut]


class KindleCaptureIdentityOut(BaseModel):
    asin: str
    title: str
    title_normalized: str | None
    authors: list[str]
    series_name: str | None
    volume_number: float | None
    volume_label: str | None


class KindleAgentJobOut(KindleCaptureJobOut):
    identity: KindleCaptureIdentityOut


class KindleAgentClaimResponse(BaseModel):
    job: KindleAgentJobOut | None


class KindleCaptureHeartbeatResponse(BaseModel):
    job_id: str
    status: str
    heartbeat_at: str


class KindleCaptureCompleteResponse(BaseModel):
    job_id: str
    status: str
    source: Literal["comic", "novel"]
    book_id: str
    captured_screens: int
