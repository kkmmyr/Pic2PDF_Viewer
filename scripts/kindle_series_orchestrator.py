from __future__ import annotations

import time
from collections.abc import Callable

from kindle_series_models import (
    TERMINAL_STATUSES,
    UNFINISHED_STATUSES,
    CaptureApi,
    FailureRecovery,
    SeriesBook,
    SeriesCaptureError,
)
from kindle_series_session import SessionSafetyGuard


def _unfinished_jobs(
    jobs: list[dict],
    *,
    except_job_id: str | None = None,
) -> list[dict]:
    return [
        job
        for job in jobs
        if job.get("status") in UNFINISHED_STATUSES
        and job.get("id") != except_job_id
    ]


def _wait_for_job(
    api: CaptureApi,
    job_id: str,
    *,
    poll_seconds: float,
    timeout_seconds: float,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
) -> dict:
    started = monotonic()
    last_status = ""
    while monotonic() - started <= timeout_seconds:
        jobs = api.list_jobs()
        others = _unfinished_jobs(jobs, except_job_id=job_id)
        if others:
            raise SeriesCaptureError(
                f"Another unfinished capture job appeared while monitoring {job_id}"
            )
        matches = [job for job in jobs if job.get("id") == job_id]
        if len(matches) != 1:
            raise SeriesCaptureError(
                f"Capture job disappeared from API history: {job_id}"
            )
        job = matches[0]
        status = str(job.get("status") or "")
        if status != last_status:
            print(
                f"  state={status} screens={job.get('captured_screens') or 0}",
                flush=True,
            )
            last_status = status
        if status in TERMINAL_STATUSES:
            return job
        sleep(poll_seconds)
    raise SeriesCaptureError(
        f"Timed out while monitoring {job_id}; the active job was not cancelled"
    )


def _recovery_candidate(result: dict) -> bool:
    return (
        result.get("error_code")
        in {"kindle_not_running", "kindle_app_exited", "kindle_ui_unavailable"}
        and result.get("started_at") is None
        and int(result.get("captured_screens") or 0) == 0
    )


class SeriesCaptureOrchestrator:
    def __init__(
        self,
        api: CaptureApi,
        guard: SessionSafetyGuard,
        *,
        poll_seconds: float,
        timeout_seconds: float,
        failure_recovery: FailureRecovery | None,
        sleep: Callable[[float], None],
        monotonic: Callable[[], float],
    ) -> None:
        self.api = api
        self.guard = guard
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds
        self.failure_recovery = failure_recovery
        self.sleep = sleep
        self.monotonic = monotonic

    def run(self, books: list[SeriesBook], *, apply: bool) -> int:
        self._validate_inventory(books)
        remaining = [book for book in books if book.capture_state == "not_captured"]
        self._print_inventory(books, remaining)
        if not apply:
            print("Dry-run only. Pass --apply to create capture jobs.", flush=True)
            return 0
        if _unfinished_jobs(self.api.list_jobs()):
            self.guard.trip("unfinished_job_before_session")

        for index, book in enumerate(remaining, start=1):
            result = self._capture_book(book, index=index, total=len(remaining))
            self._confirm_registration(book)
            self.guard.record_success(book)
            print(
                f"  registered screens={result.get('captured_screens') or 0}",
                flush=True,
            )
        print(f"Series capture completed: {len(remaining)} book(s)", flush=True)
        self.guard.complete()
        return 0

    @staticmethod
    def _validate_inventory(books: list[SeriesBook]) -> None:
        invalid = [
            book
            for book in books
            if book.capture_state in {"capture_pending", "multiple_links"}
        ]
        if not invalid:
            return
        detail = ", ".join(
            f"{book.asin}:{book.capture_state}" for book in invalid
        )
        raise SeriesCaptureError(f"Inventory contains unsafe capture states: {detail}")

    @staticmethod
    def _print_inventory(
        books: list[SeriesBook],
        remaining: list[SeriesBook],
    ) -> None:
        captured = len(books) - len(remaining)
        print(
            f"Inventory: total={len(books)} captured={captured} "
            f"remaining={len(remaining)}",
            flush=True,
        )
        for book in remaining:
            print(
                f"- {book.source} vol={book.volume_number:g} "
                f"{book.asin} {book.title}",
                flush=True,
            )

    def _capture_book(
        self,
        book: SeriesBook,
        *,
        index: int,
        total: int,
    ) -> dict:
        recovery_used = False
        while True:
            self.guard.before_create(book)
            self._reject_unfinished_job(book)
            result = self._create_and_monitor(book, index=index, total=total)
            if result.get("status") == "succeeded":
                return result
            if self._recover(book, result, recovery_used=recovery_used):
                recovery_used = True
                print(
                    f"  recovered Kindle; retrying the same ASIN {book.asin}",
                    flush=True,
                )
                continue
            self.guard.record_failure(book, result)
            raise SeriesCaptureError(
                f"Capture failed for {book.asin}: "
                f"{result.get('error_code')} {result.get('error_message')}"
            )

    def _reject_unfinished_job(self, book: SeriesBook) -> None:
        if _unfinished_jobs(self.api.list_jobs()):
            self.guard.trip(f"unfinished_job_before_create:{book.asin}")

    def _create_and_monitor(
        self,
        book: SeriesBook,
        *,
        index: int,
        total: int,
    ) -> dict:
        print(
            f"[{index}/{total}] Creating job for {book.asin} ({book.title})",
            flush=True,
        )
        try:
            job = self.api.create_job(book)
        except Exception:
            self.guard.trip(f"job_create_failed:{book.asin}")
            raise
        job_id = str(job.get("id") or "")
        if not job_id:
            self.guard.trip(f"job_create_missing_id:{book.asin}")
        try:
            return _wait_for_job(
                self.api,
                job_id,
                poll_seconds=self.poll_seconds,
                timeout_seconds=self.timeout_seconds,
                sleep=self.sleep,
                monotonic=self.monotonic,
            )
        except SeriesCaptureError:
            self.guard.trip(f"job_monitor_failed:{book.asin}")
            raise

    def _recover(
        self,
        book: SeriesBook,
        result: dict,
        *,
        recovery_used: bool,
    ) -> bool:
        if (
            self.failure_recovery is None
            or recovery_used
            or not _recovery_candidate(result)
        ):
            return False
        self.guard.record_recovery_attempt(book)
        try:
            return self.failure_recovery.recover(self.api, book, result)
        except Exception as exc:
            self.guard.trip(
                f"kindle_recovery_failed:{book.asin}:{type(exc).__name__}"
            )
            raise

    def _confirm_registration(self, book: SeriesBook) -> None:
        try:
            registered = self.api.get_book(book.asin)
        except Exception:
            self.guard.trip(f"registration_lookup_failed:{book.asin}")
            raise
        if registered.get("capture_state") != "captured":
            self.guard.trip(f"registration_unconfirmed:{book.asin}")


def execute_series(
    api: CaptureApi,
    books: list[SeriesBook],
    *,
    apply: bool,
    poll_seconds: float = 10.0,
    timeout_seconds: float = 4 * 60 * 60,
    failure_recovery: FailureRecovery | None = None,
    safety_guard: SessionSafetyGuard | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> int:
    guard = safety_guard or SessionSafetyGuard.open(books, None)
    orchestrator = SeriesCaptureOrchestrator(
        api,
        guard,
        poll_seconds=poll_seconds,
        timeout_seconds=timeout_seconds,
        failure_recovery=failure_recovery,
        sleep=sleep,
        monotonic=monotonic,
    )
    return orchestrator.run(books, apply=apply)
