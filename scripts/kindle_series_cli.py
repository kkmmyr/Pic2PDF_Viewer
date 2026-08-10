from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from kindle_series_http import HttpCaptureApi
from kindle_series_inventory import build_inventory
from kindle_series_models import (
    DEFAULT_API_BASE,
    DEFAULT_SERIES,
    FailureRecovery,
    SeriesCaptureError,
)
from kindle_series_orchestrator import execute_series
from kindle_series_session import SessionSafetyGuard


def build_parser() -> argparse.ArgumentParser:
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
        "--session-state",
        type=Path,
        help="Persistent fail-closed session state JSON (required with --apply).",
    )
    parser.add_argument(
        "--resume-session",
        action="store_true",
        help="Explicitly resume an inspected running session state.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create capture jobs. Without this option the command is a dry-run.",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    errors = (
        (
            args.apply and args.expected_total is None,
            "--expected-total is required with --apply",
        ),
        (
            args.apply and args.session_state is None,
            "--session-state is required with --apply",
        ),
        (args.resume_session and not args.apply, "--resume-session requires --apply"),
        (
            args.expected_total is not None and args.expected_total <= 0,
            "--expected-total must be greater than zero",
        ),
        (args.poll_seconds < 0, "--poll-seconds must be zero or greater"),
        (args.job_timeout_hours <= 0, "--job-timeout-hours must be greater than zero"),
        (
            args.kindle_startup_timeout_seconds <= 0,
            "--kindle-startup-timeout-seconds must be greater than zero",
        ),
    )
    for invalid, message in errors:
        if invalid:
            raise SystemExit(message)


def _failure_recovery(args: argparse.Namespace) -> FailureRecovery | None:
    if not args.recover_kindle_crash:
        return None
    kindle_pdf_dir = Path(__file__).resolve().parents[1] / "kindle-pdf"
    sys.path.insert(0, str(kindle_pdf_dir))
    from kindle_capture_recovery import KindleCrashRecovery, KindleRecoveryConfig

    return KindleCrashRecovery(
        KindleRecoveryConfig(
            startup_timeout_seconds=args.kindle_startup_timeout_seconds,
            audit_log_path=args.kindle_recovery_log,
        )
    )


def run(args: argparse.Namespace) -> int:
    api = HttpCaptureApi(args.api_base)
    books = build_inventory(
        api.list_books(args.series),
        series_name=args.series,
        expected_total=args.expected_total,
    )
    safety_guard = SessionSafetyGuard.open(
        books,
        args.session_state if args.apply else None,
        resume=args.resume_session,
    )
    return execute_series(
        api,
        books,
        apply=args.apply,
        poll_seconds=args.poll_seconds,
        timeout_seconds=args.job_timeout_hours * 60 * 60,
        failure_recovery=_failure_recovery(args),
        safety_guard=safety_guard,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    validate_args(args)
    try:
        return run(args)
    except KeyboardInterrupt:
        print("\nInterrupted. No next capture job will be created.", file=sys.stderr)
        return 130
    except SeriesCaptureError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
