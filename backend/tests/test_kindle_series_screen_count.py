from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "capture_kindle_series.py"
SPEC = importlib.util.spec_from_file_location("kindle_series_screen_count_facade", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
series_capture = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = series_capture
SPEC.loader.exec_module(series_capture)


def _book(
    asin: str,
    volume: int,
    *,
    source: str = "novel",
    capture_state: str = "not_captured",
):
    return series_capture.SeriesBook(
        asin=asin,
        title=f"book-{asin}",
        source=source,
        volume_number=float(volume),
        capture_state=capture_state,
    )


def _persisted_warning(
    *,
    source: str = "novel",
    captured_screens: int = 120,
) -> dict:
    reference_median = 300.0
    return {
        "code": "series_screen_count_outlier_candidate",
        "severity": "warning",
        "policy_version": "kindle-series-screen-count-v1",
        "asin": "N1",
        "source": source,
        "captured_screens": captured_screens,
        "reference_count": 3,
        "reference_min": 290,
        "reference_median": reference_median,
        "reference_max": 310,
        "ratio_to_median": round(captured_screens / reference_median, 6),
    }


class ScreenCountApi:
    def __init__(
        self,
        counts: dict[str, object],
        *,
        history: list[dict] | None = None,
    ) -> None:
        self.counts = counts
        self.history = history or []
        self.created: list[str] = []
        self.jobs: list[dict] = []

    def list_books(self, query: str) -> list[dict]:
        raise AssertionError(f"inventory is supplied directly: {query}")

    def list_jobs(self) -> list[dict]:
        for job in self.jobs:
            if job["status"] == "queued":
                job["status"] = "succeeded"
                job["captured_screens"] = self.counts[job["asin"]]
                job["completed_at"] = f"2026-08-22T00:00:{len(self.created):02}+00:00"
        return [dict(job) for job in reversed(self.jobs)] + [dict(job) for job in self.history]

    def create_job(self, book) -> dict:
        self.created.append(book.asin)
        job = {
            "id": f"job-{book.asin}",
            "asin": book.asin,
            "source": book.source,
            "status": "queued",
            "requested_at": f"2026-08-22T00:00:{len(self.created):02}+00:00",
        }
        self.jobs.append(job)
        return dict(job)

    def get_book(self, asin: str) -> dict:
        return {"asin": asin, "capture_state": "captured"}


def test_outlier_warning_is_persisted_without_stopping_next_job(tmp_path: Path) -> None:
    books = [_book(f"N{index}", index) for index in range(1, 6)]
    api = ScreenCountApi({"N1": 100, "N2": 102, "N3": 98, "N4": 20, "N5": 101})
    state_path = tmp_path / "session.json"
    guard = series_capture.SessionSafetyGuard.open(books, state_path)

    result = series_capture.execute_series(
        api,
        books,
        apply=True,
        poll_seconds=0,
        sleep=lambda _: None,
        safety_guard=guard,
    )

    assert result == 0
    assert api.created == ["N1", "N2", "N3", "N4", "N5"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["schema_version"] == 2
    assert state["state"] == "completed"
    assert state["captured_screens_by_asin"] == {
        "N1": 100,
        "N2": 102,
        "N3": 98,
        "N4": 20,
        "N5": 101,
    }
    assert state["quality_warnings"] == [
        {
            "code": "series_screen_count_outlier_candidate",
            "severity": "warning",
            "policy_version": "kindle-series-screen-count-v1",
            "asin": "N4",
            "source": "novel",
            "captured_screens": 20,
            "reference_count": 3,
            "reference_min": 98,
            "reference_median": 100.0,
            "reference_max": 102,
            "ratio_to_median": 0.2,
        }
    ]


def test_historical_policy_uses_latest_success_per_asin_and_same_source() -> None:
    books = [
        _book("N1", 1, capture_state="captured"),
        _book("N2", 2, capture_state="captured"),
        _book("N3", 3, capture_state="captured"),
        _book("C1", 1, source="comic", capture_state="captured"),
        _book("N4", 4),
    ]
    history = [
        {
            "id": "new-N1",
            "asin": "N1",
            "source": "novel",
            "status": "succeeded",
            "captured_screens": 100,
            "completed_at": "2026-08-22T00:04:00+00:00",
        },
        {
            "id": "comic-C1",
            "asin": "C1",
            "source": "comic",
            "status": "succeeded",
            "captured_screens": 400,
            "completed_at": "2026-08-22T00:03:00+00:00",
        },
        {
            "id": "job-N2",
            "asin": "N2",
            "source": "novel",
            "status": "succeeded",
            "captured_screens": 110,
            "completed_at": "2026-08-22T00:02:00+00:00",
        },
        {
            "id": "job-N3",
            "asin": "N3",
            "source": "novel",
            "status": "succeeded",
            "captured_screens": 90,
            "completed_at": "2026-08-22T00:01:00+00:00",
        },
        {
            "id": "old-N1",
            "asin": "N1",
            "source": "novel",
            "status": "succeeded",
            "captured_screens": 10,
            "completed_at": "2026-08-21T00:00:00+00:00",
        },
    ]
    policy = series_capture.SeriesScreenCountPolicy.from_history(
        books,
        history,
        {},
    )

    warning = policy.observe(books[-1], 30)

    assert warning is not None
    assert warning["reference_count"] == 3
    assert warning["reference_median"] == 100.0
    assert warning["ratio_to_median"] == 0.3


@pytest.mark.parametrize("captured_screens", [50, 200])
def test_policy_does_not_warn_at_inclusive_ratio_boundaries(
    captured_screens: int,
) -> None:
    books = [_book("N1", 1), _book("N2", 2), _book("N3", 3), _book("N4", 4)]
    policy = series_capture.SeriesScreenCountPolicy({"novel": {"N1": 100, "N2": 100, "N3": 100}, "comic": {}})

    assert policy.observe(books[-1], captured_screens) is None


def test_invalid_succeeded_screen_count_trips_before_next_job(tmp_path: Path) -> None:
    books = [_book("N1", 1), _book("N2", 2)]
    api = ScreenCountApi({"N1": None, "N2": 100})
    guard = series_capture.SessionSafetyGuard.open(books, tmp_path / "session.json")

    with pytest.raises(series_capture.SeriesCaptureError, match="invalid_screen_count"):
        series_capture.execute_series(
            api,
            books,
            apply=True,
            poll_seconds=0,
            sleep=lambda _: None,
            safety_guard=guard,
        )

    assert api.created == ["N1"]
    assert guard.state == "tripped"


def test_resume_preserves_screen_count_observations(tmp_path: Path) -> None:
    books = [_book("N1", 1)]
    state_path = tmp_path / "session.json"
    guard = series_capture.SessionSafetyGuard.open(books, state_path)
    guard.record_success(books[0], captured_screens=120, warning=None)

    resumed = series_capture.SessionSafetyGuard.open(books, state_path, resume=True)

    assert resumed.captured_screens_by_asin == {"N1": 120}
    assert resumed.quality_warnings == []


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "captured_screens_by_asin",
            {"UNKNOWN": 120},
            "screen-count observations",
        ),
        (
            "captured_screens_by_asin",
            {},
            "completed ASINs",
        ),
        (
            "quality_warnings",
            [
                {
                    **_persisted_warning(),
                    "ratio_to_median": 0.2,
                }
            ],
            "warning is inconsistent",
        ),
    ],
)
def test_resume_rejects_tampered_screen_count_state(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    books = [_book("N1", 1)]
    state_path = tmp_path / "session.json"
    guard = series_capture.SessionSafetyGuard.open(books, state_path)
    guard.record_success(books[0], captured_screens=120, warning=None)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state[field] = value
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(series_capture.SeriesCaptureError, match=message):
        series_capture.SessionSafetyGuard.open(books, state_path, resume=True)


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("captured_screens_by_asin", "observations are missing"),
        ("quality_warnings", "warnings are missing"),
    ],
)
def test_resume_rejects_missing_screen_count_evidence(
    tmp_path: Path,
    field: str,
    message: str,
) -> None:
    books = [_book("N1", 1)]
    state_path = tmp_path / "session.json"
    guard = series_capture.SessionSafetyGuard.open(books, state_path)
    guard.record_success(books[0], captured_screens=120, warning=None)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.pop(field)
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(series_capture.SeriesCaptureError, match=message):
        series_capture.SessionSafetyGuard.open(books, state_path, resume=True)


@pytest.mark.parametrize(
    "warning",
    [
        _persisted_warning(source="comic"),
        _persisted_warning(captured_screens=119),
    ],
)
def test_resume_rejects_warning_that_does_not_match_observation(
    tmp_path: Path,
    warning: dict,
) -> None:
    books = [_book("N1", 1)]
    state_path = tmp_path / "session.json"
    guard = series_capture.SessionSafetyGuard.open(books, state_path)
    guard.record_success(books[0], captured_screens=120, warning=None)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["quality_warnings"] = [warning]
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(series_capture.SeriesCaptureError, match="does not match"):
        series_capture.SessionSafetyGuard.open(books, state_path, resume=True)


def test_resume_rejects_legacy_schema_v1(tmp_path: Path) -> None:
    books = [_book("N1", 1)]
    state_path = tmp_path / "session.json"
    series_capture.SessionSafetyGuard.open(books, state_path)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["schema_version"] = 1
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(series_capture.SeriesCaptureError, match="does not match"):
        series_capture.SessionSafetyGuard.open(books, state_path, resume=True)
