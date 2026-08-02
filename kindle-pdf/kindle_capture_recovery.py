"""Fail-closed Kindle process recovery for sequential capture runners."""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from kindle_app_controller import (
    BookIdentity,
    KindleAppController,
    KindleControllerError,
)

DEFAULT_KINDLE_APP_ID = "AMZNKindle.AmazonKindleReadingApp_m1sc522ngdk36!App"
RECOVERABLE_ERROR_CODES = frozenset(
    {"kindle_not_running", "kindle_app_exited", "kindle_ui_unavailable"}
)
UNFINISHED_JOB_STATUSES = frozenset(
    {
        "queued",
        "claimed",
        "locating_book",
        "downloading",
        "positioning",
        "waiting_user",
        "capturing",
        "awaiting_files",
    }
)


class RecoveryApi(Protocol):
    def list_jobs(self) -> list[dict]: ...


class RecoveryBook(Protocol):
    asin: str
    title: str


class KindleRecoveryError(RuntimeError):
    """A recovery attempt started but could not reach a verified safe state."""


@dataclass(frozen=True)
class KindleRecoveryConfig:
    startup_timeout_seconds: float = 60.0
    poll_seconds: float = 1.0
    app_user_model_id: str = DEFAULT_KINDLE_APP_ID
    audit_log_path: Path | None = None


def kindle_is_running() -> bool:
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Kindle.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return '"kindle.exe"' in result.stdout.casefold()


def launch_kindle(app_user_model_id: str) -> None:
    subprocess.Popen(
        ["explorer.exe", f"shell:AppsFolder\\{app_user_model_id}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _job_is_pre_capture_process_failure(job: dict) -> bool:
    if job.get("status") != "failed":
        return False
    if job.get("error_code") not in RECOVERABLE_ERROR_CODES:
        return False
    if job.get("started_at") is not None:
        return False
    return int(job.get("captured_screens") or 0) == 0


class KindleCrashRecovery:
    """Restart Kindle and re-verify one ASIN before allowing a replacement job."""

    def __init__(
        self,
        config: KindleRecoveryConfig | None = None,
        *,
        process_running: Callable[[], bool] = kindle_is_running,
        launcher: Callable[[str], None] = launch_kindle,
        controller_factory: Callable[[], KindleAppController] = KindleAppController,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config or KindleRecoveryConfig()
        if self.config.startup_timeout_seconds <= 0:
            raise ValueError("startup_timeout_seconds must be greater than zero")
        if self.config.poll_seconds < 0:
            raise ValueError("poll_seconds must be zero or greater")
        self._process_running = process_running
        self._launcher = launcher
        self._controller_factory = controller_factory
        self._sleep = sleep
        self._monotonic = monotonic
        self._attempts: dict[str, int] = {}

    def recover(self, api: RecoveryApi, book: RecoveryBook, failed_job: dict) -> bool:
        """Return True only after Kindle and the exact target ASIN are verified."""
        attempts = self._attempts.get(book.asin, 0)
        if not self._can_recover(api, book, failed_job, attempts):
            return False

        attempt = attempts + 1
        self._attempts[book.asin] = attempt
        self._record(book, failed_job, attempt=attempt, outcome="started")
        self._launcher(self.config.app_user_model_id)

        last_error = self._wait_until_verified(api, book)
        if last_error is None:
            self._record(book, failed_job, attempt=attempt, outcome="verified")
            return True
        self._record(
            book,
            failed_job,
            attempt=attempt,
            outcome="failed",
            detail=last_error,
        )
        raise KindleRecoveryError(
            f"Kindle restart verification timed out for {book.asin}: {last_error}"
        )

    def _can_recover(
        self,
        api: RecoveryApi,
        book: RecoveryBook,
        failed_job: dict,
        attempts: int,
    ) -> bool:
        if not _job_is_pre_capture_process_failure(failed_job):
            return False
        if str(failed_job.get("asin") or "").casefold() != book.asin.casefold():
            return False
        if attempts >= 1:
            return False
        if self._process_running():
            # Never kill a live process automatically. A live but unusable UI needs
            # direct diagnosis because it may be showing login/update/modal state.
            return False
        return not self._unfinished_jobs(api)

    def _wait_until_verified(
        self,
        api: RecoveryApi,
        book: RecoveryBook,
    ) -> str | None:
        identity = BookIdentity(asin=book.asin, title=book.title)
        deadline = self._monotonic() + self.config.startup_timeout_seconds
        last_error = "Kindle.exe did not start"
        while self._monotonic() <= deadline:
            if not self._process_running():
                self._sleep(self.config.poll_seconds)
                continue
            controller = self._controller_factory()
            try:
                controller.attach_running_app()
                candidate = controller.search_book(identity)
                if (
                    candidate.asin is None
                    or candidate.asin.casefold() != book.asin.casefold()
                ):
                    raise KindleRecoveryError(
                        "Kindle recovery candidate did not expose the expected ASIN"
                    )
                if self._unfinished_jobs(api):
                    raise KindleRecoveryError(
                        "Another unfinished capture job appeared during Kindle recovery"
                    )
                return None
            except KindleRecoveryError:
                raise
            except KindleControllerError as exc:
                if exc.error_code in {
                    "book_identity_unverified",
                    "book_match_ambiguous",
                }:
                    raise KindleRecoveryError(str(exc)) from exc
                last_error = f"{exc.error_code}: {exc}"
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            self._sleep(self.config.poll_seconds)
        return last_error

    @staticmethod
    def _unfinished_jobs(api: RecoveryApi) -> list[dict]:
        return [
            job
            for job in api.list_jobs()
            if job.get("status") in UNFINISHED_JOB_STATUSES
        ]

    def _record(
        self,
        book: RecoveryBook,
        failed_job: dict,
        *,
        attempt: int,
        outcome: str,
        detail: str | None = None,
    ) -> None:
        path = self.config.audit_log_path
        if path is None:
            return
        payload = {
            "recorded_at": datetime.now().astimezone().isoformat(),
            "asin": book.asin,
            "failed_job_id": failed_job.get("id"),
            "error_code": failed_job.get("error_code"),
            "attempt": attempt,
            "outcome": outcome,
            "detail": detail,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False) + "\n")


__all__ = [
    "KindleCrashRecovery",
    "KindleRecoveryConfig",
    "KindleRecoveryError",
    "kindle_is_running",
    "launch_kindle",
]
