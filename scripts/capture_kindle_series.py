"""Capture a Kindle series sequentially through the Pic2PDFViewer API.

This module remains the command and import compatibility facade.  The implementation
is split into inventory, session safety, orchestration, HTTP, and CLI modules.
"""

# ruff: noqa: E402

from __future__ import annotations

import sys
import time
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) in sys.path:
    sys.path.remove(str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR))

from kindle_series_cli import build_parser as _parser
from kindle_series_cli import main, validate_args
from kindle_series_http import HttpCaptureApi
from kindle_series_inventory import (
    _japanese_number,
    _source_from_title,
    _volume_from_title,
    build_inventory,
)
from kindle_series_models import (
    DEFAULT_API_BASE,
    DEFAULT_SERIES,
    LABEL_SOURCES,
    SOURCE_ORDER,
    TERMINAL_STATUSES,
    UNFINISHED_STATUSES,
    CaptureApi,
    FailureRecovery,
    SeriesBook,
    SeriesCaptureError,
)
from kindle_series_orchestrator import (
    _recovery_candidate,
    _unfinished_jobs,
    _wait_for_job,
    execute_series,
)
from kindle_series_session import SessionSafetyGuard

_COMPATIBILITY_EXPORTS = (
    time,
    _parser,
    _japanese_number,
    _source_from_title,
    _volume_from_title,
    _unfinished_jobs,
    _wait_for_job,
    _recovery_candidate,
    validate_args,
)

__all__ = [
    "CaptureApi",
    "DEFAULT_API_BASE",
    "DEFAULT_SERIES",
    "FailureRecovery",
    "HttpCaptureApi",
    "LABEL_SOURCES",
    "SOURCE_ORDER",
    "SeriesBook",
    "SeriesCaptureError",
    "SessionSafetyGuard",
    "TERMINAL_STATUSES",
    "UNFINISHED_STATUSES",
    "build_inventory",
    "execute_series",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
