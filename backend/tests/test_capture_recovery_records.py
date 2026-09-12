"""Recovery markers fail closed before publication and after interrupted writes."""

import json
from datetime import datetime
from pathlib import Path

import pytest

import config
from services.kindle_catalog import capture_recovery_record, capture_registration
from services.kindle_catalog.capture_publication import CapturePublication
from services.kindle_catalog.capture_recovery import resume_rollback
from services.kindle_catalog.capture_recovery_record import (
    CaptureRollbackError,
    read_record,
    recovery_lock,
    recovery_path,
    require_no_pending_recovery,
)
from services.kindle_catalog.connection import with_db
from tests import test_capture_recovery as recovery_fixtures

prepared_job = recovery_fixtures.prepared_job
published = recovery_fixtures.published


def test_initial_marker_write_failure_happens_before_publication(prepared_job, monkeypatch):
    def fail(_descriptor) -> None:
        raise OSError("marker sync failed")

    monkeypatch.setattr(capture_recovery_record.os, "fsync", fail)
    with pytest.raises(OSError, match="marker sync failed"):
        capture_registration.complete(prepared_job["id"], "windows-1", completed_at=datetime(2026, 9, 12))
    target = Path(config.get_dirs_by_source("comic")["img"]) / prepared_job["title"]
    assert not target.exists()
    assert Path(config.KINDLE_CAPTURE_INBOX_DIR, f"{prepared_job['id']}.ready", "manifest.json").is_file()
    with pytest.raises(RuntimeError, match="撮影復旧記録"):
        require_no_pending_recovery()


def test_marker_cannot_be_replaced_by_a_second_publication(published):
    capture = published
    path = recovery_path(capture.job["id"])
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        capture.begin()
    assert path.read_bytes() == before
    assert (capture.backup_target / "001.png").read_bytes() == b"old-image"


def test_broken_marker_blocks_both_publication_and_resume(published):
    capture = published
    recovery_path(capture.job["id"]).write_text("{", encoding="utf-8")
    with pytest.raises(RuntimeError, match="撮影復旧記録"):
        require_no_pending_recovery()
    with pytest.raises(json.JSONDecodeError):
        resume_rollback(capture.job["id"])
    assert (capture.backup_target / "001.png").read_bytes() == b"old-image"


def test_successful_job_is_not_rolled_back_when_marker_removal_fails(prepared_job, monkeypatch, caplog):
    def fail(_self) -> None:
        raise OSError("marker is locked")

    monkeypatch.setattr(CapturePublication, "clear_recovery", fail)
    # Alembic fixture setup can disable loggers created before its configuration.
    monkeypatch.setattr(capture_registration.logger, "disabled", False)
    monkeypatch.setattr(capture_registration.logger, "propagate", True)
    result = capture_registration.complete(prepared_job["id"], "windows-1", completed_at=datetime(2026, 9, 12))
    assert result["status"] == "succeeded"
    record = read_record(prepared_job["id"])
    assert Path(record.paths["target"], "001.png").is_file()
    assert Path(record.paths["processed_package"], "manifest.json").is_file()
    with with_db() as conn:
        assert (
            conn.execute("SELECT status FROM capture_jobs WHERE id=?", (prepared_job["id"],)).fetchone()[0]
            == "succeeded"
        )
    assert "Capture succeeded but recovery marker cleanup failed" in caplog.text


def test_completed_compensation_can_retry_marker_removal_alone(published):
    capture = published

    def fail() -> None:
        raise OSError("marker is locked")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(capture, "clear_recovery", fail)
        with pytest.raises(CaptureRollbackError):
            capture.rollback()
    assert not any(read_record(capture.job["id"]).pending.model_dump().values())
    resume_rollback(capture.job["id"])
    assert (capture.target / "001.png").read_bytes() == b"old-image"
    assert not recovery_path(capture.job["id"]).exists()


def test_missing_backup_is_reported_and_generation_is_retained(published):
    capture = published
    held = capture.backup_target.with_name("temporarily-held")
    capture.backup_target.rename(held)
    with pytest.raises(CaptureRollbackError) as caught:
        capture.rollback()
    assert any(isinstance(error, FileNotFoundError) for error in caught.value.failures)
    assert (held / "001.png").read_bytes() == b"old-image"
    assert read_record(capture.job["id"]).pending.existing_backed_up is True
    held.rename(capture.backup_target)
    resume_rollback(capture.job["id"])
    assert (capture.target / "001.png").read_bytes() == b"old-image"


def test_foreign_target_prevents_backup_overwrite(published):
    capture = published
    remove = capture._remove_directory

    def replace_with_foreign(path: Path) -> None:
        remove(path)
        if path == capture.target:
            path.mkdir()
            (path / "foreign").write_bytes(b"preserve")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(capture, "_remove_directory", replace_with_foreign)
        with pytest.raises(CaptureRollbackError):
            capture.rollback()
    with pytest.raises(CaptureRollbackError):
        resume_rollback(capture.job["id"])
    assert (capture.target / "foreign").read_bytes() == b"preserve"
    assert (capture.backup_target / "001.png").read_bytes() == b"old-image"


def test_recovery_lock_rejects_duplicate_resume_and_publication(published):
    capture = published
    with recovery_lock(capture.job["id"]):
        with pytest.raises(FileExistsError):
            resume_rollback(capture.job["id"])
        with pytest.raises(RuntimeError, match="撮影復旧記録"):
            require_no_pending_recovery()
        assert (capture.backup_target / "001.png").read_bytes() == b"old-image"
    assert not recovery_path(capture.job["id"]).with_suffix(".lock").exists()
