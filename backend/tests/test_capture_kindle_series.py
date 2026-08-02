"""Tests for the safe Kindle series capture orchestrator."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "capture_kindle_series.py"
SPEC = importlib.util.spec_from_file_location("capture_kindle_series", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
series_capture = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = series_capture
SPEC.loader.exec_module(series_capture)


def _item(
    asin: str,
    title: str,
    volume: float,
    capture_state: str = "not_captured",
) -> dict:
    return {
        "asin": asin,
        "title": title,
        "series_name": "茉莉花官吏伝",
        "ownership": "purchased",
        "volume_number": volume,
        "capture_state": capture_state,
    }


class FakeApi:
    def __init__(self, outcomes: dict[str, str]) -> None:
        self.outcomes = outcomes
        self.created: list[str] = []
        self.jobs: list[dict] = []

    def list_books(self, query: str) -> list[dict]:
        raise AssertionError("inventory is supplied directly")

    def list_jobs(self) -> list[dict]:
        for job in self.jobs:
            if job["status"] == "queued":
                job["status"] = self.outcomes[job["asin"]]
                if job["status"] == "failed":
                    job["error_code"] = "capture_failed"
                    job["error_message"] = "test failure"
                else:
                    job["captured_screens"] = 10
        return [dict(job) for job in self.jobs]

    def create_job(self, book) -> dict:
        self.created.append(book.asin)
        job = {"id": f"job-{book.asin}", "asin": book.asin, "status": "queued"}
        self.jobs.append(job)
        return dict(job)

    def get_book(self, asin: str) -> dict:
        return {"asin": asin, "capture_state": "captured"}


class RecoveringFakeApi(FakeApi):
    def __init__(self, outcomes: dict[str, list[str]]) -> None:
        super().__init__({})
        self.remaining_outcomes = {asin: list(values) for asin, values in outcomes.items()}

    def list_jobs(self) -> list[dict]:
        for job in self.jobs:
            if job["status"] != "queued":
                continue
            outcome = self.remaining_outcomes[job["asin"]].pop(0)
            job["status"] = outcome
            if outcome == "failed":
                job["error_code"] = "kindle_app_exited"
                job["error_message"] = "test crash"
                job["started_at"] = None
                job["captured_screens"] = None
            else:
                job["captured_screens"] = 10
        return [dict(job) for job in self.jobs]

    def create_job(self, book) -> dict:
        self.created.append(book.asin)
        attempt = sum(job["asin"] == book.asin for job in self.jobs) + 1
        suffix = "" if attempt == 1 else f"-{attempt}"
        job = {
            "id": f"job-{book.asin}{suffix}",
            "asin": book.asin,
            "status": "queued",
        }
        self.jobs.append(job)
        return dict(job)


class FakeRecovery:
    def __init__(self, decisions: list[bool]) -> None:
        self.decisions = list(decisions)
        self.calls: list[tuple[str, str]] = []

    def recover(self, _api, book, failed_job: dict) -> bool:
        self.calls.append((book.asin, failed_job["id"]))
        return self.decisions.pop(0)


def test_inventory_uses_label_source_and_sorts_novel_before_comic():
    books = series_capture.build_inventory(
        [
            _item(
                "COMIC2",
                "茉莉花官吏伝～後宮女官、気ままな生活～ 2 (プリンセス・コミックス)",
                2,
            ),
            _item("NOVEL8", "茉莉花官吏伝 八 (ビーズログ文庫)", 8),
            _item(
                "COMIC1",
                "茉莉花官吏伝～後宮女官、気ままな生活～ 1 (プリンセス・コミックス)",
                1,
            ),
        ],
        series_name="茉莉花官吏伝",
        expected_total=3,
    )

    assert [(book.asin, book.source) for book in books] == [
        ("NOVEL8", "novel"),
        ("COMIC1", "comic"),
        ("COMIC2", "comic"),
    ]


def test_inventory_derives_known_novel_volumes_from_title():
    raw = [
        {
            **_item(
                "NOVEL18",
                "茉莉花官吏伝 十八　青龍の睛を点ずる (ビーズログ文庫)",
                18,
            ),
            "volume_number": None,
        },
        {
            **_item(
                "NOVEL1",
                "茉莉花官吏伝　皇帝の恋心、花知らず (ビーズログ文庫)",
                1,
            ),
            "volume_number": None,
        },
    ]

    books = series_capture.build_inventory(
        raw,
        series_name="茉莉花官吏伝",
        expected_total=2,
    )

    assert [(book.asin, book.volume_number) for book in books] == [
        ("NOVEL1", 1.0),
        ("NOVEL18", 18.0),
    ]


def test_dry_run_does_not_create_jobs():
    api = FakeApi({})
    books = series_capture.build_inventory(
        [_item("NOVEL8", "茉莉花官吏伝 八 (ビーズログ文庫)", 8)],
        series_name="茉莉花官吏伝",
        expected_total=1,
    )

    assert series_capture.execute_series(api, books, apply=False) == 0
    assert api.created == []


def test_apply_requires_expected_total_before_api_access():
    with pytest.raises(SystemExit, match="--expected-total is required with --apply"):
        series_capture.main(["--apply"])


def test_apply_requires_persistent_session_state_before_api_access():
    with pytest.raises(SystemExit, match="--session-state is required"):
        series_capture.main(["--apply", "--expected-total", "1"])


def test_apply_creates_next_job_only_after_previous_success():
    api = FakeApi({"NOVEL8": "succeeded", "NOVEL9": "succeeded"})
    books = series_capture.build_inventory(
        [
            _item("NOVEL9", "茉莉花官吏伝 九 (ビーズログ文庫)", 9),
            _item("NOVEL8", "茉莉花官吏伝 八 (ビーズログ文庫)", 8),
        ],
        series_name="茉莉花官吏伝",
        expected_total=2,
    )

    result = series_capture.execute_series(
        api,
        books,
        apply=True,
        poll_seconds=0,
        sleep=lambda _: None,
    )

    assert result == 0
    assert api.created == ["NOVEL8", "NOVEL9"]


def test_apply_stops_before_next_job_when_a_book_fails():
    api = FakeApi({"NOVEL8": "failed", "NOVEL9": "succeeded"})
    books = series_capture.build_inventory(
        [
            _item("NOVEL8", "茉莉花官吏伝 八 (ビーズログ文庫)", 8),
            _item("NOVEL9", "茉莉花官吏伝 九 (ビーズログ文庫)", 9),
        ],
        series_name="茉莉花官吏伝",
        expected_total=2,
    )

    with pytest.raises(series_capture.SeriesCaptureError, match="breaker tripped"):
        series_capture.execute_series(
            api,
            books,
            apply=True,
            poll_seconds=0,
            sleep=lambda _: None,
        )

    assert api.created == ["NOVEL8"]


def test_apply_retries_only_the_same_book_after_verified_recovery():
    api = RecoveringFakeApi({"NOVEL8": ["failed", "succeeded"], "NOVEL9": ["succeeded"]})
    recovery = FakeRecovery([True])
    books = series_capture.build_inventory(
        [
            _item("NOVEL8", "茉莉花官吏伝 八 (ビーズログ文庫)", 8),
            _item("NOVEL9", "茉莉花官吏伝 九 (ビーズログ文庫)", 9),
        ],
        series_name="茉莉花官吏伝",
        expected_total=2,
    )

    result = series_capture.execute_series(
        api,
        books,
        apply=True,
        poll_seconds=0,
        sleep=lambda _: None,
        failure_recovery=recovery,
    )

    assert result == 0
    assert api.created == ["NOVEL8", "NOVEL8", "NOVEL9"]
    assert recovery.calls == [("NOVEL8", "job-NOVEL8")]


def test_apply_does_not_create_next_job_when_recovery_rejects_failure():
    api = RecoveringFakeApi({"NOVEL8": ["failed"], "NOVEL9": ["succeeded"]})
    recovery = FakeRecovery([False])
    books = series_capture.build_inventory(
        [
            _item("NOVEL8", "茉莉花官吏伝 八 (ビーズログ文庫)", 8),
            _item("NOVEL9", "茉莉花官吏伝 九 (ビーズログ文庫)", 9),
        ],
        series_name="茉莉花官吏伝",
        expected_total=2,
    )

    with pytest.raises(series_capture.SeriesCaptureError, match="breaker tripped"):
        series_capture.execute_series(
            api,
            books,
            apply=True,
            poll_seconds=0,
            sleep=lambda _: None,
            failure_recovery=recovery,
        )

    assert api.created == ["NOVEL8"]
    assert recovery.calls == [("NOVEL8", "job-NOVEL8")]


def test_apply_never_recovers_the_same_book_twice():
    api = RecoveringFakeApi({"NOVEL8": ["failed", "failed"]})
    recovery = FakeRecovery([True, True])
    books = series_capture.build_inventory(
        [_item("NOVEL8", "茉莉花官吏伝 八 (ビーズログ文庫)", 8)],
        series_name="茉莉花官吏伝",
        expected_total=1,
    )

    with pytest.raises(series_capture.SeriesCaptureError, match="breaker tripped"):
        series_capture.execute_series(
            api,
            books,
            apply=True,
            poll_seconds=0,
            sleep=lambda _: None,
            failure_recovery=recovery,
        )

    assert api.created == ["NOVEL8", "NOVEL8"]
    assert recovery.calls == [("NOVEL8", "job-NOVEL8")]


def test_session_breaker_limits_recovery_across_different_books():
    api = RecoveringFakeApi({"NOVEL8": ["failed", "succeeded"], "NOVEL9": ["failed"]})
    recovery = FakeRecovery([True, True])
    books = series_capture.build_inventory(
        [
            _item("NOVEL8", "茉莉花官吏伝 八 (ビーズログ文庫)", 8),
            _item("NOVEL9", "茉莉花官吏伝 九 (ビーズログ文庫)", 9),
        ],
        series_name="茉莉花官吏伝",
        expected_total=2,
    )

    with pytest.raises(series_capture.SeriesCaptureError, match="recovery_limit"):
        series_capture.execute_series(
            api,
            books,
            apply=True,
            poll_seconds=0,
            sleep=lambda _: None,
            failure_recovery=recovery,
        )

    assert api.created == ["NOVEL8", "NOVEL8", "NOVEL9"]
    assert recovery.calls == [("NOVEL8", "job-NOVEL8")]


def test_session_state_requires_explicit_matching_resume(tmp_path):
    books = series_capture.build_inventory(
        [_item("NOVEL8", "茉莉花官吏伝 八 (ビーズログ文庫)", 8)],
        series_name="茉莉花官吏伝",
        expected_total=1,
    )
    state_path = tmp_path / "session.json"
    guard = series_capture.SessionSafetyGuard.open(books, state_path)
    guard.record_recovery_attempt(books[0])

    with pytest.raises(series_capture.SeriesCaptureError, match="explicit resume"):
        series_capture.SessionSafetyGuard.open(books, state_path)

    resumed = series_capture.SessionSafetyGuard.open(
        books,
        state_path,
        resume=True,
    )
    assert resumed.kindle_recovery_attempts == 1
    with pytest.raises(series_capture.SeriesCaptureError, match="recovery_limit"):
        resumed.record_recovery_attempt(books[0])
    assert json.loads(state_path.read_text(encoding="utf-8"))["state"] == "tripped"


def test_apply_rejects_an_existing_unfinished_job():
    api = FakeApi({})
    api.jobs.append({"id": "other", "asin": "OTHER", "status": "capturing"})
    books = series_capture.build_inventory(
        [_item("NOVEL8", "茉莉花官吏伝 八 (ビーズログ文庫)", 8)],
        series_name="茉莉花官吏伝",
        expected_total=1,
    )

    with pytest.raises(series_capture.SeriesCaptureError, match="unfinished_job"):
        series_capture.execute_series(api, books, apply=True)

    assert api.created == []
