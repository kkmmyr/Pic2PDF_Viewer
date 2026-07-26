"""OCR実行、QA、ground truth、agent APIのスキーマ。"""

from typing import Literal

from pydantic import BaseModel

PageType = Literal["unknown", "narrative", "toc", "illustration", "colophon_or_ad"]
LayoutType = Literal["unknown", "normal_prose", "full_width", "mixed_illustration", "structured", "image_only"]


class OcrRunResponse(BaseModel):
    status: str
    job_id: int
    queue_position: int


class OcrStopResponse(BaseModel):
    status: str
    canceled_jobs: list[int]


class OcrQaRunSummary(BaseModel):
    id: int
    book_name: str
    engine: str
    model: str
    source_page_count: int
    state: str
    qa_state: str
    required_pages: int
    approved_pages: int
    rejected_pages: int
    started_at: str | None


class OcrQaRunListResponse(BaseModel):
    runs: list[OcrQaRunSummary]


class OcrQaPageOut(BaseModel):
    page_no: int
    state: str
    qa_state: str
    full_text: str
    char_count: int
    quality_flags: list[str]
    ink_coverage: float | None
    attempt_count: int
    error_message: str | None
    qa_note: str | None
    reviewed_at: str | None
    page_type: PageType
    layout_type: LayoutType
    primary_text: str
    external_text: str
    selected_engine: Literal["primary", "external", "codex"]
    corrected_text: str | None
    index_eligible: bool
    image_url: str


class OcrQaRunDetail(OcrQaRunSummary):
    qa_reviewer: str | None
    qa_reviewed_at: str | None
    qa_note: str | None
    pages: list[OcrQaPageOut]


class OcrQaPageReviewRequest(BaseModel):
    state: Literal["approved", "rejected"]
    note: str | None = None
    page_type: PageType
    layout_type: LayoutType
    selected_engine: Literal["primary", "external", "codex"]
    corrected_text: str | None = None


class OcrQaRunApproveRequest(BaseModel):
    reviewer: str
    note: str | None = None


class OcrQaActionResponse(BaseModel):
    status: str
    run_id: int


class OcrPageTypeClassificationResponse(BaseModel):
    status: str
    run_id: int
    counts: dict[str, int]


class OcrGroundTruthSeedSample(BaseModel):
    run_id: int
    page_no: int


class OcrGroundTruthSeedRequest(BaseModel):
    samples: list[OcrGroundTruthSeedSample]


class OcrGroundTruthSeedResponse(BaseModel):
    status: str
    created: int


class OcrGroundTruthUpdateRequest(BaseModel):
    reference_text: str | None = None
    page_type: PageType
    layout_type: LayoutType
    state: Literal["draft", "verified"]
    note: str | None = None


class OcrGroundTruthEntryOut(BaseModel):
    id: int
    run_id: int
    page_no: int
    image_sha256: str
    page_type: PageType
    layout_type: LayoutType
    reference_text: str
    state: Literal["draft", "verified"]
    note: str | None
    created_at: str | None
    updated_at: str | None
    verified_at: str | None
    book_name: str
    ocr_text: str
    edit_distance: int | None
    reference_chars: int | None
    cer: float | None
    image_url: str


class OcrGroundTruthMetricOut(BaseModel):
    page_type: PageType
    total_count: int
    verified_count: int
    total_edit_distance: int
    total_reference_chars: int
    aggregate_cer: float | None


class OcrGroundTruthLayoutMetricOut(BaseModel):
    layout_type: LayoutType
    total_count: int
    verified_count: int
    total_edit_distance: int
    total_reference_chars: int
    aggregate_cer: float | None


class OcrGroundTruthListResponse(BaseModel):
    entries: list[OcrGroundTruthEntryOut]
    total_count: int
    verified_count: int
    total_edit_distance: int
    total_reference_chars: int
    aggregate_cer: float | None
    metrics_by_page_type: list[OcrGroundTruthMetricOut]
    metrics_by_layout_type: list[OcrGroundTruthLayoutMetricOut]


class OcrAgentClaimRequest(BaseModel):
    agent_id: str


class OcrAgentTaskOut(BaseModel):
    book_name: str
    page_no: int
    image_sha256: str
    image_url: str


class OcrAgentBookOut(BaseModel):
    book_name: str
    run_id: int
    source_page_count: int
    tasks: list[OcrAgentTaskOut]


class OcrAgentJobOut(BaseModel):
    id: int
    job_type: str
    target_id: str | None
    agent_id: str
    progress_total: int
    progress_done: int
    books: list[OcrAgentBookOut]


class OcrAgentClaimResponse(BaseModel):
    job: OcrAgentJobOut | None


class OcrAgentHeartbeatRequest(BaseModel):
    agent_id: str


class OcrAgentPageResultIn(BaseModel):
    page_no: int
    image_sha256: str
    state: str
    full_text: str
    char_count: int
    raw_output: str
    block_count: int
    quality_flags: list[str]
    ink_coverage: float | None
    attempt_count: int
    server_generation: int | None = None
    error_message: str | None = None
    layout_type: LayoutType = "unknown"
    primary_text: str | None = None
    external_text: str | None = None
    selected_engine: Literal["primary", "external"] = "primary"


class OcrAgentPageSubmitRequest(BaseModel):
    agent_id: str
    book_name: str
    page: OcrAgentPageResultIn


class OcrAgentFailRequest(BaseModel):
    agent_id: str
    error: str


class OcrAgentActionResponse(BaseModel):
    job_id: int
    status: str
    book_name: str | None = None
    page_no: int | None = None
    books: int | None = None
