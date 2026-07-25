"""Kindle 購入カタログの SQLModel スキーマ定義。"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlmodel import Field, SQLModel, UniqueConstraint


class KindleSQLModel(SQLModel):
    """既存 novel DB と同名テーブルが衝突しない専用メタデータ。"""

    metadata = MetaData()


class Book(KindleSQLModel, table=True):
    __tablename__ = "books"  # type: ignore[reportAssignmentType]

    asin: str = Field(primary_key=True, max_length=20)
    title: str
    title_normalized: str | None = Field(default=None, index=True)
    publisher: str | None = None
    isbn: str | None = None
    isbn13: str | None = None
    category: str = Field(default="unknown", index=True)
    book_type: str = Field(default="unknown", index=True)
    kindle_acquisition_date: str | None = Field(default=None, index=True)
    total_reading_ms: int | None = None
    last_read_at: str | None = None
    is_completed: bool | None = Field(default=None, index=True)
    created_at: str | None = None
    updated_at: str | None = None


class Author(KindleSQLModel, table=True):
    __tablename__ = "authors"  # type: ignore[reportAssignmentType]

    id: int | None = Field(default=None, primary_key=True)
    name: str
    name_key: str = Field(unique=True, index=True)


class BookAuthor(KindleSQLModel, table=True):
    __tablename__ = "book_authors"  # type: ignore[reportAssignmentType]
    __table_args__ = (UniqueConstraint("asin", "author_id"),)

    id: int | None = Field(default=None, primary_key=True)
    asin: str = Field(foreign_key="books.asin", index=True)
    author_id: int = Field(foreign_key="authors.id", index=True)
    sort_order: int = 0


class BookGenre(KindleSQLModel, table=True):
    __tablename__ = "book_genres"  # type: ignore[reportAssignmentType]
    __table_args__ = (UniqueConstraint("asin", "genre"),)

    id: int | None = Field(default=None, primary_key=True)
    asin: str = Field(foreign_key="books.asin", index=True)
    genre: str = Field(index=True)


class ImportedFile(KindleSQLModel, table=True):
    __tablename__ = "imported_files"  # type: ignore[reportAssignmentType]
    __table_args__ = (UniqueConstraint("source_kind", "filename", "sha256"),)

    id: int | None = Field(default=None, primary_key=True)
    source_kind: str = Field(index=True)
    filename: str
    sha256: str = Field(max_length=64)
    imported_at: str
    record_count: int | None = None
    status: str = Field(default="success", index=True)


class ImportRun(KindleSQLModel, table=True):
    __tablename__ = "import_runs"  # type: ignore[reportAssignmentType]

    id: int | None = Field(default=None, primary_key=True)
    source_kind: str = Field(index=True)
    status: str = Field(index=True)
    started_at: str
    finished_at: str | None = None
    files_processed: int = 0
    records_processed: int = 0
    records_skipped: int = 0
    error_message: str | None = None


class Purchase(KindleSQLModel, table=True):
    __tablename__ = "purchases"  # type: ignore[reportAssignmentType]
    __table_args__ = (UniqueConstraint("order_number", "asin", "title"),)

    id: int | None = Field(default=None, primary_key=True)
    order_number: str = Field(index=True)
    order_date: str = Field(index=True)
    asin: str | None = Field(default=None, foreign_key="books.asin", index=True)
    title: str
    price: int | None = None
    order_status: str = Field(default="SUCCESS", index=True)
    digital_order_item_id: str | None = None
    source_file_id: int | None = Field(default=None, foreign_key="imported_files.id")
    created_at: str | None = None


class Borrowing(KindleSQLModel, table=True):
    __tablename__ = "borrowings"  # type: ignore[reportAssignmentType]
    __table_args__ = (UniqueConstraint("asin", "loan_creation_date"),)

    id: int | None = Field(default=None, primary_key=True)
    asin: str = Field(foreign_key="books.asin", index=True)
    title: str
    authors: str | None = None
    loan_program: str | None = None
    loan_status: str = Field(index=True)
    loan_creation_date: str = Field(index=True)
    loan_acceptance_date: str | None = None
    end_date: str | None = None
    source_file_id: int | None = Field(default=None, foreign_key="imported_files.id")
    created_at: str | None = None


class Return(KindleSQLModel, table=True):
    __tablename__ = "returns"  # type: ignore[reportAssignmentType]
    __table_args__ = (UniqueConstraint("asin", "order_id", "return_date"),)

    id: int | None = Field(default=None, primary_key=True)
    asin: str = Field(foreign_key="books.asin", index=True)
    title: str
    order_id: str | None = Field(default=None, index=True)
    refund_amount: int | None = None
    return_date: str = Field(index=True)
    return_status: str | None = None
    source_file_id: int | None = Field(default=None, foreign_key="imported_files.id")
    created_at: str | None = None


class Series(KindleSQLModel, table=True):
    __tablename__ = "series"  # type: ignore[reportAssignmentType]
    __table_args__ = (UniqueConstraint("name", "author_key"),)

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    author: str | None = None
    author_key: str = ""
    created_at: str | None = None
    updated_at: str | None = None


class BookSeries(KindleSQLModel, table=True):
    __tablename__ = "book_series"  # type: ignore[reportAssignmentType]

    asin: str = Field(primary_key=True, foreign_key="books.asin")
    series_id: int = Field(foreign_key="series.id", index=True)
    volume_number: float | None = None
    volume_label: str | None = None
    detection_method: str | None = None
    is_manually_edited: bool = False
    confidence: float | None = None
    updated_at: str | None = None


class SeriesSubscription(KindleSQLModel, table=True):
    __tablename__ = "series_subscriptions"  # type: ignore[reportAssignmentType]

    series_asin: str = Field(primary_key=True)
    subscription_id: str
    title: str
    series_id: int | None = Field(default=None, foreign_key="series.id", index=True)
    resolution_method: str | None = None
    imported_at: str | None = None


class CaptureJob(KindleSQLModel, table=True):
    __tablename__ = "capture_jobs"  # type: ignore[reportAssignmentType]

    id: str = Field(primary_key=True)
    asin: str = Field(foreign_key="books.asin", index=True)
    source: str = Field(index=True)
    status: str = Field(default="queued", index=True)
    direction: str = "left"
    expected_screens: int | None = None
    requested_at: str
    claimed_at: str | None = None
    heartbeat_at: str | None = Field(default=None, index=True)
    started_at: str | None = None
    completed_at: str | None = None
    agent_id: str | None = Field(default=None, index=True)
    book_id: str | None = None
    captured_screens: int | None = None
    error_code: str | None = None
    error_message: str | None = None
