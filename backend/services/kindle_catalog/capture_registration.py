"""検証済みcapture packageの登録workflow。"""

from datetime import datetime
from pathlib import Path

import config
from services.kindle_catalog.capture_package_validator import validate_ready_dir
from services.kindle_catalog.capture_publication import CapturePublication
from services.kindle_catalog.capture_registration_repository import (
    load_awaiting_job,
    mark_succeeded,
)


def _inject_failure(_point: str) -> None:
    """障害注入テスト用。productionでは何もしない。"""


def complete(
    job_id: str,
    agent_id: str,
    *,
    completed_at: datetime,
) -> dict:
    """`<job_id>.ready`を検証し、正式領域へatomic publishする。"""
    job = load_awaiting_job(job_id, agent_id)
    ready_dir = Path(config.KINDLE_CAPTURE_INBOX_DIR) / f"{job_id}.ready"
    _manifest, files = validate_ready_dir(job, ready_dir)
    _inject_failure("after_ready_validation")
    publication = CapturePublication(job, ready_dir, completed_at)
    try:
        publication.stage(files)
        _inject_failure("after_staging_copy")
        publication.backup_existing()
        if publication.replacing_existing:
            _inject_failure("after_existing_backup")
        publication.publish_target()
        _inject_failure("after_target_publish")
        publication.update_meta()
        _inject_failure("after_meta_update")
        publication.archive_package()
        _inject_failure("after_package_archive")
        _inject_failure("before_job_update")
        mark_succeeded(
            job_id,
            agent_id,
            completed_at=completed_at,
            book_id=publication.book_id,
            captured_screens=len(files),
        )
    except Exception:
        publication.rollback()
        raise
    return {
        "job_id": job_id,
        "status": "succeeded",
        "source": job["source"],
        "book_id": publication.book_id,
        "captured_screens": len(files),
    }
