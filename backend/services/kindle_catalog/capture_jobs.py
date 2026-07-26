"""Kindle capture jobの後方互換service facade。"""

import config
from services.kindle_catalog import capture_job_repository as repository
from services.kindle_catalog import capture_registration as registration
from services.kindle_catalog.capture_package_validator import (
    safe_title as _safe_title,
)
from services.kindle_catalog.capture_package_validator import (
    validate_ready_dir as _validate_ready_dir,
)
from utils.dt import jst_now

ACTIVE_STATUSES = repository.ACTIVE_STATUSES
_AGENT_TRANSITIONS = repository.AGENT_TRANSITIONS
_row_dict = repository.row_dict
_recover_stale = repository._recover_stale

_COMPATIBILITY_EXPORTS = (
    _AGENT_TRANSITIONS,
    _row_dict,
    _recover_stale,
    _safe_title,
    _validate_ready_dir,
)


def create(
    asin: str,
    source: str,
    direction: str,
    expected_screens: int | None,
) -> dict:
    return repository.create(
        asin,
        source,
        direction,
        expected_screens,
        requested_at=jst_now(),
    )


def list_jobs(limit: int = 100) -> list[dict]:
    return repository.list_jobs(limit)


def claim(agent_id: str) -> dict | None:
    return repository.claim(
        agent_id,
        now=jst_now(),
        timeout_seconds=config.KINDLE_CAPTURE_HEARTBEAT_TIMEOUT_SEC,
    )


def heartbeat(job_id: str, agent_id: str) -> dict:
    return repository.heartbeat(job_id, agent_id, now=jst_now())


def update_state(
    job_id: str,
    agent_id: str,
    state: str,
    *,
    captured_screens: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict:
    return repository.update_state(
        job_id,
        agent_id,
        state,
        now=jst_now(),
        captured_screens=captured_screens,
        error_code=error_code,
        error_message=error_message,
    )


def complete(job_id: str, agent_id: str) -> dict:
    return registration.complete(job_id, agent_id, completed_at=jst_now())
