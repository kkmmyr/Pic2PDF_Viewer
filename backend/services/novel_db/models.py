"""novel.db の SQLModel テーブル定義（スキーマの唯一の真実の源）。

`table=True` クラスは SQLAlchemy metadata に登録され、
`alembic revision --autogenerate` でのスキーマ差分検出に使用される。

既存の sqlite3 ベースクエリはそのまま動作し続ける。
将来的には SQLAlchemy Session 経由のクエリに順次移行する。

pages_fts は FTS5 仮想テーブルのため SQLModel では定義せず、
Alembic の include_name フィルタで autogenerate 対象外にする。
"""

from __future__ import annotations

from sqlmodel import Field, SQLModel, UniqueConstraint


class Book(SQLModel, table=True):
    __tablename__ = "books"  # type: ignore[reportAssignmentType]

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    pdf_path: str
    images_dir: str
    page_count: int
    indexed_at: str | None = None
    created_at: str | None = None
    summary: str | None = None
    summary_generated_at: str | None = None
    ocr_done_at: str | None = None


class Page(SQLModel, table=True):
    __tablename__ = "pages"  # type: ignore[reportAssignmentType]
    __table_args__ = (UniqueConstraint("book_id", "page_no"),)

    id: int | None = Field(default=None, primary_key=True)
    book_id: int = Field(foreign_key="books.id")
    page_no: int
    image_path: str | None = None
    full_text: str | None = None
    char_count: int
    main_characters: str | None = None
    page_type: str = "narrative"
    index_eligible: bool = True


class Chunk(SQLModel, table=True):
    __tablename__ = "chunks"  # type: ignore[reportAssignmentType]

    id: int | None = Field(default=None, primary_key=True)
    page_id: int = Field(foreign_key="pages.id")
    chunk_idx: int
    text: str
    char_count: int
    contextual_text: str | None = None
    contextual_generated_at: str | None = None


class QAHistory(SQLModel, table=True):
    __tablename__ = "qa_history"  # type: ignore[reportAssignmentType]

    id: int | None = Field(default=None, primary_key=True)
    asked_at: str | None = None
    finished_at: str | None = None
    scope_type: str
    scope_id: str | None = None
    question: str
    answer: str | None = None
    prompt: str
    context_json: str
    model: str
    options_json: str
    eval_count: int | None = None
    done_reason: str | None = None
    error_message: str | None = None


class BookCharacter(SQLModel, table=True):
    __tablename__ = "book_characters"  # type: ignore[reportAssignmentType]
    __table_args__ = (UniqueConstraint("book_id", "name"),)

    id: int | None = Field(default=None, primary_key=True)
    book_id: int = Field(foreign_key="books.id")
    name: str
    summary: str | None = None
    first_page: int
    page_count: int
    generated_at: str | None = None


class QASession(SQLModel, table=True):
    __tablename__ = "qa_sessions"  # type: ignore[reportAssignmentType]

    id: int | None = Field(default=None, primary_key=True)
    scope_type: str
    scope_id: str | None = None
    title: str | None = None
    started_at: str | None = None
    last_message_at: str | None = None


class QAMessage(SQLModel, table=True):
    __tablename__ = "qa_messages"  # type: ignore[reportAssignmentType]

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="qa_sessions.id")
    role: str
    content: str
    eval_count: int | None = None
    done_reason: str | None = None
    created_at: str | None = None


class RebuildJob(SQLModel, table=True):
    __tablename__ = "rebuild_jobs"  # type: ignore[reportAssignmentType]

    id: int | None = Field(default=None, primary_key=True)
    job_type: str
    target_id: str | None = None
    mode: str = "rebuild"
    state: str = "queued"
    enqueued_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    progress_total: int | None = None
    progress_done: int | None = None
    error_message: str | None = None
    current_step: str | None = None
    current_detail: str | None = None
    agent_id: str | None = None
    heartbeat_at: str | None = None


class OcrRun(SQLModel, table=True):
    __tablename__ = "ocr_runs"  # type: ignore[reportAssignmentType]

    id: int | None = Field(default=None, primary_key=True)
    book_name: str
    engine: str
    model: str
    source_page_count: int
    state: str = "running"
    started_at: str | None = None
    finished_at: str | None = None
    error_message: str | None = None
    qa_state: str = "pending"
    qa_reviewer: str | None = None
    qa_reviewed_at: str | None = None
    qa_note: str | None = None


class OcrPageResult(SQLModel, table=True):
    __tablename__ = "ocr_page_results"  # type: ignore[reportAssignmentType]
    __table_args__ = (UniqueConstraint("run_id", "page_no"),)

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="ocr_runs.id")
    page_no: int
    image_sha256: str
    state: str
    full_text: str | None = None
    char_count: int = 0
    raw_output: str | None = None
    block_count: int = 0
    quality_flags_json: str = "[]"
    ink_coverage: float | None = None
    attempt_count: int = 0
    error_message: str | None = None
    updated_at: str | None = None
    qa_state: str = "not_required"
    qa_note: str | None = None
    reviewed_at: str | None = None
    page_type: str = "unknown"
    layout_type: str = "unknown"
    primary_text: str | None = None
    external_text: str | None = None
    selected_engine: str = "primary"
    corrected_text: str | None = None
    index_eligible: bool = False


class OcrAgentJobRun(SQLModel, table=True):
    __tablename__ = "ocr_agent_job_runs"  # type: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint("job_id", "book_name"),
        UniqueConstraint("job_id", "run_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="rebuild_jobs.id")
    run_id: int = Field(foreign_key="ocr_runs.id")
    book_name: str


class OcrGroundTruthPage(SQLModel, table=True):
    __tablename__ = "ocr_ground_truth_pages"  # type: ignore[reportAssignmentType]
    __table_args__ = (UniqueConstraint("run_id", "page_no"),)

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="ocr_runs.id")
    page_no: int
    image_sha256: str
    page_type: str = "unknown"
    layout_type: str = "unknown"
    reference_text: str | None = None
    state: str = "draft"
    note: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    verified_at: str | None = None
