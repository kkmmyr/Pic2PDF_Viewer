"""Capture a Kindle series sequentially through the Pic2PDFViewer API."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

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


class HttpCaptureApi:
    def __init__(self, api_base: str, timeout_seconds: float = 30.0) -> None:
        self.api_base = api_base.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, object] | None = None,
        body: dict[str, object] | None = None,
    ) -> dict:
        url = f"{self.api_base}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise SeriesCaptureError(
                f"API request failed: {method} {path}: {exc}"
            ) from exc

    def list_books(self, query: str) -> list[dict]:
        response = self._request(
            "GET",
            "/api/kindle-catalog/books",
            query={"q": query, "page": 1, "page_size": 200},
        )
        items = response.get("items")
        if not isinstance(items, list):
            raise SeriesCaptureError("Catalog response does not contain an items list")
        if response.get("total") != len(items):
            raise SeriesCaptureError(
                "Series search exceeded the supported 200-book inventory"
            )
        return items

    def list_jobs(self) -> list[dict]:
        response = self._request(
            "GET",
            "/api/kindle-catalog/capture-jobs",
            query={"limit": 500},
        )
        items = response.get("items")
        if not isinstance(items, list):
            raise SeriesCaptureError(
                "Capture job response does not contain an items list"
            )
        return items

    def create_job(self, book: SeriesBook) -> dict:
        return self._request(
            "POST",
            "/api/kindle-catalog/capture-jobs",
            body={
                "asin": book.asin,
                "source": book.source,
                "direction": "left",
                "expected_screens": None,
            },
        )

    def get_book(self, asin: str) -> dict:
        response = self._request(
            "GET",
            "/api/kindle-catalog/books",
            query={"q": asin, "page": 1, "page_size": 50},
        )
        matches = [
            item for item in response.get("items", []) if item.get("asin") == asin
        ]
        if len(matches) != 1:
            raise SeriesCaptureError(
                f"Catalog did not return exactly one book for ASIN {asin}"
            )
        return matches[0]


def _source_from_title(title: str) -> str:
    matches = [source for label, source in LABEL_SOURCES.items() if label in title]
    if len(matches) != 1:
        raise SeriesCaptureError(f"Cannot safely classify Kindle source: {title}")
    return matches[0]


def _japanese_number(value: str) -> int | None:
    digits = {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if value in digits:
        return digits[value]
    if value == "十":
        return 10
    if "十" in value:
        tens, ones = value.split("十", 1)
        if tens not in {"", *digits} or ones not in {"", *digits}:
            return None
        return digits.get(tens, 1) * 10 + digits.get(ones, 0)
    return None


def _volume_from_title(title: str, *, series_name: str, source: str) -> float | None:
    if source == "comic":
        match = re.search(r"[ 　](\d+)[ 　]*\(プリンセス・コミックス\)$", title)
        return float(match.group(1)) if match else None
    match = re.match(
        rf"^{re.escape(series_name)}[ 　]+([一二三四五六七八九十]+)(?:[ 　]|$)",
        title,
    )
    if match:
        number = _japanese_number(match.group(1))
        return float(number) if number is not None else None
    if series_name == DEFAULT_SERIES and title.startswith(f"{series_name}　"):
        return 1.0
    return None


def build_inventory(
    items: list[dict],
    *,
    series_name: str,
    expected_total: int | None,
) -> list[SeriesBook]:
    books: list[SeriesBook] = []
    seen_asins: set[str] = set()
    for item in items:
        title = str(item.get("title") or "")
        catalog_series = str(item.get("series_name") or "")
        if series_name not in title and catalog_series != series_name:
            continue
        if item.get("ownership") != "purchased":
            raise SeriesCaptureError(
                f"Series item is not a purchased book: {item.get('asin')} {title}"
            )
        asin = str(item.get("asin") or "")
        if not asin or asin in seen_asins:
            raise SeriesCaptureError(
                f"Missing or duplicate ASIN in series inventory: {asin}"
            )
        source = _source_from_title(title)
        volume_number = item.get("volume_number")
        if not isinstance(volume_number, (int, float)):
            volume_number = _volume_from_title(
                title,
                series_name=series_name,
                source=source,
            )
        if volume_number is None:
            raise SeriesCaptureError(
                f"Cannot safely determine volume number: {asin} {title}"
            )
        capture_state = str(item.get("capture_state") or "")
        if capture_state not in {
            "not_captured",
            "captured",
            "capture_pending",
            "multiple_links",
        }:
            raise SeriesCaptureError(
                f"Unknown capture state for {asin}: {capture_state}"
            )
        books.append(
            SeriesBook(
                asin=asin,
                title=title,
                source=source,
                volume_number=float(volume_number),
                capture_state=capture_state,
            )
        )
        seen_asins.add(asin)

    books.sort(key=lambda book: book.sort_key)
    if expected_total is not None and len(books) != expected_total:
        raise SeriesCaptureError(
            f"Expected {expected_total} series books, but catalog returned {len(books)}"
        )
    if not books:
        raise SeriesCaptureError(f"No purchased books found for series: {series_name}")
    return books


def _unfinished_jobs(
    jobs: list[dict], *, except_job_id: str | None = None
) -> list[dict]:
    return [
        job
        for job in jobs
        if job.get("status") in UNFINISHED_STATUSES and job.get("id") != except_job_id
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


def execute_series(
    api: CaptureApi,
    books: list[SeriesBook],
    *,
    apply: bool,
    poll_seconds: float = 10.0,
    timeout_seconds: float = 4 * 60 * 60,
    failure_recovery: FailureRecovery | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> int:
    invalid = [
        book
        for book in books
        if book.capture_state in {"capture_pending", "multiple_links"}
    ]
    if invalid:
        detail = ", ".join(f"{book.asin}:{book.capture_state}" for book in invalid)
        raise SeriesCaptureError(f"Inventory contains unsafe capture states: {detail}")

    remaining = [book for book in books if book.capture_state == "not_captured"]
    captured = len(books) - len(remaining)
    print(
        f"Inventory: total={len(books)} captured={captured} remaining={len(remaining)}",
        flush=True,
    )
    for book in remaining:
        print(
            f"- {book.source} vol={book.volume_number:g} {book.asin} {book.title}",
            flush=True,
        )
    if not apply:
        print("Dry-run only. Pass --apply to create capture jobs.", flush=True)
        return 0
    if _unfinished_jobs(api.list_jobs()):
        raise SeriesCaptureError(
            "An unfinished capture job already exists; nothing was created"
        )

    for index, book in enumerate(remaining, start=1):
        recovery_used = False
        while True:
            if _unfinished_jobs(api.list_jobs()):
                raise SeriesCaptureError(
                    "An unfinished capture job exists before the next book"
                )
            print(
                f"[{index}/{len(remaining)}] Creating job for {book.asin} ({book.title})",
                flush=True,
            )
            job = api.create_job(book)
            job_id = str(job.get("id") or "")
            if not job_id:
                raise SeriesCaptureError(
                    f"Create job response has no id for {book.asin}"
                )
            result = _wait_for_job(
                api,
                job_id,
                poll_seconds=poll_seconds,
                timeout_seconds=timeout_seconds,
                sleep=sleep,
                monotonic=monotonic,
            )
            if result.get("status") == "succeeded":
                break
            recovered = False
            if failure_recovery is not None and not recovery_used:
                try:
                    recovered = failure_recovery.recover(api, book, result)
                except Exception as exc:
                    raise SeriesCaptureError(
                        f"Capture recovery failed for {book.asin}: {exc}"
                    ) from exc
            if recovered:
                recovery_used = True
                print(
                    f"  recovered Kindle; retrying the same ASIN {book.asin}",
                    flush=True,
                )
                continue
            raise SeriesCaptureError(
                f"Capture failed for {book.asin}: "
                f"{result.get('error_code')} {result.get('error_message')}"
            )
        registered = api.get_book(book.asin)
        if registered.get("capture_state") != "captured":
            raise SeriesCaptureError(
                f"Job succeeded but formal registration is not confirmed for {book.asin}"
            )
        print(
            f"  registered screens={result.get('captured_screens') or 0}",
            flush=True,
        )
    print(f"Series capture completed: {len(remaining)} book(s)", flush=True)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely create one Kindle capture job at a time for a series."
    )
    parser.add_argument("--series", default=DEFAULT_SERIES)
    parser.add_argument("--expected-total", type=int)
    parser.add_argument(
        "--api-base",
        default=os.getenv("PIC2PDF_API_URL", DEFAULT_API_BASE),
    )
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    parser.add_argument("--job-timeout-hours", type=float, default=4.0)
    parser.add_argument(
        "--recover-kindle-crash",
        action="store_true",
        help=(
            "Restart a missing Kindle process and retry the same pre-capture job "
            "only after exact ASIN verification."
        ),
    )
    parser.add_argument("--kindle-startup-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--kindle-recovery-log", type=Path)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create capture jobs. Without this option the command is a dry-run.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.apply and args.expected_total is None:
        raise SystemExit("--expected-total is required with --apply")
    if args.expected_total is not None and args.expected_total <= 0:
        raise SystemExit("--expected-total must be greater than zero")
    if args.poll_seconds < 0:
        raise SystemExit("--poll-seconds must be zero or greater")
    if args.job_timeout_hours <= 0:
        raise SystemExit("--job-timeout-hours must be greater than zero")
    if args.kindle_startup_timeout_seconds <= 0:
        raise SystemExit("--kindle-startup-timeout-seconds must be greater than zero")
    try:
        api = HttpCaptureApi(args.api_base)
        books = build_inventory(
            api.list_books(args.series),
            series_name=args.series,
            expected_total=args.expected_total,
        )
        failure_recovery = None
        if args.recover_kindle_crash:
            kindle_pdf_dir = Path(__file__).resolve().parents[1] / "kindle-pdf"
            sys.path.insert(0, str(kindle_pdf_dir))
            from kindle_capture_recovery import (  # noqa: PLC0415
                KindleCrashRecovery,
                KindleRecoveryConfig,
            )

            failure_recovery = KindleCrashRecovery(
                KindleRecoveryConfig(
                    startup_timeout_seconds=args.kindle_startup_timeout_seconds,
                    audit_log_path=args.kindle_recovery_log,
                )
            )
        return execute_series(
            api,
            books,
            apply=args.apply,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.job_timeout_hours * 60 * 60,
            failure_recovery=failure_recovery,
        )
    except KeyboardInterrupt:
        print("\nInterrupted. No next capture job will be created.", file=sys.stderr)
        return 130
    except SeriesCaptureError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
