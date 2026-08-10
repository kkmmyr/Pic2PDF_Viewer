from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

DEFAULT_API_BASE = "http://medaroserver:8090"
DEFAULT_SERIES = "茉莉花官吏伝"
LABEL_SOURCES = {
    "ビーズログ文庫": "novel",
    "プリンセス・コミックス": "comic",
}
SOURCE_ORDER = {"novel": 0, "comic": 1}
UNFINISHED_STATUSES = {
    "queued",
    "claimed",
    "locating_book",
    "downloading",
    "positioning",
    "waiting_user",
    "capturing",
    "awaiting_files",
}
TERMINAL_STATUSES = {"succeeded", "failed"}


class SeriesCaptureError(RuntimeError):
    """Stop the series before another capture job is created."""


@dataclass(frozen=True)
class SeriesBook:
    asin: str
    title: str
    source: str
    volume_number: float
    capture_state: str

    @property
    def sort_key(self) -> tuple[int, float, str]:
        return (SOURCE_ORDER[self.source], self.volume_number, self.asin)


class CaptureApi(Protocol):
    def list_books(self, query: str) -> list[dict]: ...

    def list_jobs(self) -> list[dict]: ...

    def create_job(self, book: SeriesBook) -> dict: ...

    def get_book(self, asin: str) -> dict: ...


class FailureRecovery(Protocol):
    def recover(
        self,
        api: CaptureApi,
        book: SeriesBook,
        failed_job: dict,
    ) -> bool: ...
