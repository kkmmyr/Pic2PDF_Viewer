from __future__ import annotations

from dataclasses import dataclass

import pytest

from kindle_app_controller import BookCandidate, KindleControllerError
from kindle_capture_recovery import (
    KindleCrashRecovery,
    KindleRecoveryConfig,
    KindleRecoveryError,
)


@dataclass(frozen=True)
class _Book:
    asin: str = "B012345678"
    title: str = "対象書籍"


class _Api:
    def __init__(self, jobs: list[dict] | None = None) -> None:
        self.jobs = jobs or []

    def list_jobs(self) -> list[dict]:
        return [dict(job) for job in self.jobs]


class _Controller:
    def __init__(self, asin: str = "B012345678") -> None:
        self.asin = asin
        self.attached = False
        self.identities = []

    def attach_running_app(self) -> None:
        self.attached = True

    def search_book(self, identity):
        self.identities.append(identity)
        return BookCandidate(asin=self.asin, title="対象書籍")


def _failed_job(**overrides) -> dict:
    value = {
        "id": "job-1",
        "asin": "B012345678",
        "status": "failed",
        "error_code": "kindle_app_exited",
        "started_at": None,
        "captured_screens": None,
    }
    value.update(overrides)
    return value


def test_recovery_launches_and_verifies_exact_asin() -> None:
    running = iter([False, True])
    launched: list[str] = []
    controller = _Controller()
    recovery = KindleCrashRecovery(
        KindleRecoveryConfig(poll_seconds=0),
        process_running=lambda: next(running),
        launcher=lambda app_id: launched.append(app_id),
        controller_factory=lambda: controller,
        sleep=lambda _seconds: None,
    )

    assert recovery.recover(_Api(), _Book(), _failed_job())
    assert len(launched) == 1
    assert controller.attached
    assert [identity.asin for identity in controller.identities] == ["B012345678"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"error_code": "download_failed"},
        {"started_at": "2026-08-02T01:00:00+09:00"},
        {"captured_screens": 1},
        {"asin": "B999999999"},
    ],
)
def test_recovery_rejects_non_pre_capture_or_wrong_target(overrides: dict) -> None:
    launched: list[str] = []
    recovery = KindleCrashRecovery(
        process_running=lambda: False,
        launcher=lambda app_id: launched.append(app_id),
    )

    assert not recovery.recover(_Api(), _Book(), _failed_job(**overrides))
    assert launched == []


def test_recovery_never_kills_or_restarts_a_live_kindle_process() -> None:
    launched: list[str] = []
    recovery = KindleCrashRecovery(
        process_running=lambda: True,
        launcher=lambda app_id: launched.append(app_id),
    )

    assert not recovery.recover(_Api(), _Book(), _failed_job())
    assert launched == []


def test_recovery_rejects_another_unfinished_job() -> None:
    launched: list[str] = []
    recovery = KindleCrashRecovery(
        process_running=lambda: False,
        launcher=lambda app_id: launched.append(app_id),
    )

    assert not recovery.recover(
        _Api([{"id": "other", "status": "capturing"}]),
        _Book(),
        _failed_job(),
    )
    assert launched == []


def test_recovery_limit_is_fail_closed_after_one_verified_attempt() -> None:
    launched: list[str] = []
    controller = _Controller()
    states = iter([False, True])
    recovery = KindleCrashRecovery(
        KindleRecoveryConfig(poll_seconds=0),
        process_running=lambda: next(states),
        launcher=lambda app_id: launched.append(app_id),
        controller_factory=lambda: controller,
        sleep=lambda _seconds: None,
    )

    assert recovery.recover(_Api(), _Book(), _failed_job())
    assert not recovery.recover(_Api(), _Book(), _failed_job(id="job-2"))
    assert len(launched) == 1


def test_recovery_fails_when_candidate_asin_is_not_exact() -> None:
    controller = _Controller(asin="B999999999")
    states = iter([False, True])
    recovery = KindleCrashRecovery(
        KindleRecoveryConfig(poll_seconds=0),
        process_running=lambda: next(states),
        launcher=lambda _app_id: None,
        controller_factory=lambda: controller,
        sleep=lambda _seconds: None,
    )

    with pytest.raises(KindleRecoveryError, match="expected ASIN"):
        recovery.recover(_Api(), _Book(), _failed_job())


def test_recovery_stops_immediately_on_ambiguous_identity() -> None:
    class _AmbiguousController(_Controller):
        def search_book(self, _identity):
            raise KindleControllerError(
                "book_match_ambiguous",
                "候補が複数あります",
            )

    states = iter([False, True])
    recovery = KindleCrashRecovery(
        KindleRecoveryConfig(poll_seconds=0),
        process_running=lambda: next(states),
        launcher=lambda _app_id: None,
        controller_factory=_AmbiguousController,
        sleep=lambda _seconds: None,
    )

    with pytest.raises(KindleRecoveryError, match="候補が複数"):
        recovery.recover(_Api(), _Book(), _failed_job())
