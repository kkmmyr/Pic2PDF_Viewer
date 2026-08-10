from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "capture_kindle_series.py"
SPEC = importlib.util.spec_from_file_location("kindle_series_module_facade", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
series_capture = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = series_capture
SPEC.loader.exec_module(series_capture)


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--apply"], "--expected-total is required with --apply"),
        (
            ["--apply", "--expected-total", "1"],
            "--session-state is required with --apply",
        ),
        (["--resume-session"], "--resume-session requires --apply"),
        (["--expected-total", "0"], "--expected-total must be greater than zero"),
        (["--poll-seconds", "-1"], "--poll-seconds must be zero or greater"),
        (
            ["--job-timeout-hours", "0"],
            "--job-timeout-hours must be greater than zero",
        ),
        (
            ["--kindle-startup-timeout-seconds", "0"],
            "--kindle-startup-timeout-seconds must be greater than zero",
        ),
    ],
)
def test_cli_validation_is_independent_from_api_access(
    argv: list[str],
    message: str,
) -> None:
    args = series_capture._parser().parse_args(argv)

    with pytest.raises(SystemExit, match=message):
        series_capture.validate_args(args)


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (
            {
                "error_code": "kindle_app_exited",
                "started_at": None,
                "captured_screens": 0,
            },
            True,
        ),
        (
            {
                "error_code": "kindle_ui_unavailable",
                "started_at": None,
                "captured_screens": None,
            },
            True,
        ),
        (
            {
                "error_code": "capture_failed",
                "started_at": None,
                "captured_screens": 0,
            },
            False,
        ),
        (
            {
                "error_code": "kindle_app_exited",
                "started_at": "2026-08-10T00:00:00Z",
                "captured_screens": 0,
            },
            False,
        ),
        (
            {
                "error_code": "kindle_app_exited",
                "started_at": None,
                "captured_screens": 1,
            },
            False,
        ),
    ],
)
def test_recovery_candidate_remains_pre_capture_only(
    result: dict,
    expected: bool,
) -> None:
    assert series_capture._recovery_candidate(result) is expected
