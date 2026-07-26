"""Persistence operations for novel database background-job state."""

from __future__ import annotations

import sqlite3

import config
from utils.logger import get_logger

from .connection import with_db

logger = get_logger(__name__)


def claim_next_job() -> dict | None:
    with with_db() as conn:
        row = conn.execute(
            "SELECT id, job_type, target_id, mode FROM rebuild_jobs "
            "WHERE state='queued' AND NOT (mode='ocr' AND ?) ORDER BY enqueued_at LIMIT 1",
            (config.app_settings.OCR_AGENT_ENABLED,),
        ).fetchone()
        if row is None:
            return None
        job_id, job_type, target_id, mode = row
        conn.execute(
            "UPDATE rebuild_jobs SET state='running', started_at=datetime('now', '+9 hours') WHERE id = ?",
            (job_id,),
        )
        conn.commit()
    return {"id": job_id, "job_type": job_type, "target_id": target_id, "mode": mode}


def mark_finished(job_id: int, state: str, *, error: str | None = None) -> None:
    with with_db() as conn:
        conn.execute(
            "UPDATE rebuild_jobs SET state = ?, finished_at = datetime('now', '+9 hours'), "
            "error_message = ? WHERE id = ?",
            (state, error, job_id),
        )
        conn.commit()


def update_progress(job_id: int, done: int, total: int) -> None:
    with with_db() as conn:
        conn.execute(
            "UPDATE rebuild_jobs SET progress_done = ?, progress_total = ? WHERE id = ?",
            (done, total, job_id),
        )
        conn.commit()


def update_step(job_id: int, step: str) -> None:
    with with_db() as conn:
        conn.execute(
            "UPDATE rebuild_jobs SET current_step = ? WHERE id = ?",
            (step, job_id),
        )
        conn.commit()


def update_detail(job_id: int, detail: str) -> None:
    try:
        with with_db() as conn:
            # Full Build may retain a long write transaction. This field is
            # advisory UI status, so skip only this update under contention.
            conn.execute("PRAGMA busy_timeout = 0")
            conn.execute(
                "UPDATE rebuild_jobs SET current_detail = ? WHERE id = ?",
                (detail, job_id),
            )
            conn.commit()
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).casefold():
            raise
        logger.debug("Job %d detail update skipped because novel.db is locked", job_id)
