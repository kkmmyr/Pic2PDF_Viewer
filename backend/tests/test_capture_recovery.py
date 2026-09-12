"""Failure injection against real capture assets and persistent recovery records."""

import json
from datetime import datetime
from pathlib import Path

import pytest

import config
from services.kindle_catalog import capture_publication, capture_registration
from services.kindle_catalog.capture_publication import CapturePublication
from services.kindle_catalog.capture_recovery import resume_rollback
from services.kindle_catalog.capture_recovery_record import (
    CaptureRollbackError,
    read_record,
    recovery_path,
    require_no_pending_recovery,
    save_record,
)
from services.kindle_catalog.capture_registration_repository import load_awaiting_job
from services.kindle_catalog.connection import with_db
from services.meta_store import load_meta, update_meta_locked
from tests.test_kindle_capture_rollback import _prepare_ready_job
from tools.recover_capture import main


@pytest.fixture
def prepared_job(tmp_data_dir, tmp_path, monkeypatch, make_png):
    inbox = tmp_path / "capture-inbox"
    monkeypatch.setattr(config, "KINDLE_CAPTURE_INBOX_DIR", str(inbox))
    job = _prepare_ready_job(inbox, make_png)
    return load_awaiting_job(job["id"], "windows-1")


@pytest.fixture
def published(prepared_job):
    job = prepared_job
    target = Path(config.get_dirs_by_source("comic")["img"]) / job["title"]
    target.mkdir(parents=True)
    (target / "001.png").write_bytes(b"old-image")
    update_meta_locked(
        "comic", lambda data: data.update({f"{job['title']}.pdf": {"authors": ["old"], "asin": job["asin"]}})
    )
    capture = CapturePublication(
        job, Path(config.KINDLE_CAPTURE_INBOX_DIR) / f"{job['id']}.ready", datetime(2026, 9, 12)
    )
    capture.begin()
    capture.stage([capture.ready_dir / "images/001.png"])
    capture.backup_existing()
    capture.publish_target()
    capture.update_meta()
    capture.archive_package()
    # Represent an incomplete staging cleanup alongside a published target.
    capture.staging.mkdir()
    (capture.staging / "leftover").write_bytes(b"partial")
    return capture


def fail_step(patch: pytest.MonkeyPatch, capture: CapturePublication, step: str, error: Exception) -> None:
    def fail() -> None:
        raise error

    methods = {
        "meta": "_restore_meta",
        "package": "_restore_package",
        "backup": "_restore_backup",
        "generation": "_remove_generation",
    }
    if step in methods:
        patch.setattr(capture, methods[step], fail)
        return
    path = capture.staging if step == "staging" else capture.target
    original = capture._remove_directory

    def remove(candidate: Path) -> None:
        if candidate == path:
            raise error
        original(candidate)

    patch.setattr(capture, "_remove_directory", remove)


@pytest.mark.parametrize(
    ("step", "pending"),
    [
        ("meta", {"meta_updated"}),
        ("package", {"archived"}),
        ("staging", {"staging_pending"}),
        ("target", {"target_published", "existing_backed_up", "generation_pending"}),
        ("backup", {"existing_backed_up", "generation_pending"}),
        ("generation", {"generation_pending"}),
    ],
)
def test_each_failure_is_recorded_and_resumed_from_disk(published, step, pending):
    capture = published
    error = OSError(f"failed {step}")
    with pytest.MonkeyPatch.context() as patch:
        fail_step(patch, capture, step, error)
        with pytest.raises(CaptureRollbackError) as caught:
            capture.rollback()
    assert caught.value.failures[0] is error
    record = read_record(capture.job["id"])
    assert {name for name, value in record.pending.model_dump().items() if value} == pending
    if "existing_backed_up" in pending:
        assert (capture.backup_target / "001.png").read_bytes() == b"old-image"
    else:
        assert (capture.target / "001.png").read_bytes() == b"old-image"
    with pytest.raises(RuntimeError, match="撮影復旧記録"):
        require_no_pending_recovery()
    # Recreate the publication from its persisted state; do not reuse the object.
    resume_rollback(capture.job["id"])
    assert (capture.target / "001.png").read_bytes() == b"old-image"
    assert capture.ready_dir.joinpath("manifest.json").is_file()
    assert not capture.staging.exists()
    assert not capture.backup_generation.exists()
    assert not recovery_path(capture.job["id"]).exists()
    assert load_awaiting_job(capture.job["id"], "windows-1")["status"] == "awaiting_files"


def test_multiple_failures_keep_old_images_and_retry_only_unfinished_steps(published):
    capture = published
    errors = [OSError("meta"), OSError("package"), OSError("target")]
    with pytest.MonkeyPatch.context() as patch:
        for step, error in zip(("meta", "package", "target"), errors, strict=True):
            fail_step(patch, capture, step, error)
        with pytest.raises(CaptureRollbackError) as caught:
            capture.rollback()
    assert caught.value.failures[:3] == errors
    assert not capture.staging.exists()
    assert capture.processed_package.is_dir()
    assert (capture.backup_target / "001.png").read_bytes() == b"old-image"
    capture.rollback()
    update_meta_locked("comic", lambda data: data[capture.book_id].update({"view_count": 99}))
    capture.rollback()
    assert (capture.target / "001.png").read_bytes() == b"old-image"
    assert load_meta("comic")[capture.book_id]["view_count"] == 99


def test_registration_error_and_compensation_error_are_both_retained(prepared_job, monkeypatch):
    original = RuntimeError("registration failed")
    compensation = OSError("metadata restore failed")

    def fail(point: str) -> None:
        if point == "before_job_update":
            raise original

    def restore(_self) -> None:
        raise compensation

    with monkeypatch.context() as patch:
        patch.setattr(capture_registration, "_inject_failure", fail)
        patch.setattr(CapturePublication, "_restore_meta", restore)
        with pytest.raises(CaptureRollbackError) as caught:
            capture_registration.complete(prepared_job["id"], "windows-1", completed_at=datetime(2026, 9, 12))
    assert isinstance(caught.value.__cause__, ExceptionGroup)
    assert caught.value.__cause__.exceptions == (original, compensation)
    record = read_record(prepared_job["id"])
    assert record.registration_failure == "RuntimeError: registration failed"
    assert record.pending.meta_updated is True
    assert not Path(record.paths["target"]).exists()
    with pytest.raises(RuntimeError, match="撮影復旧記録"):
        capture_registration.complete(prepared_job["id"], "windows-1", completed_at=datetime(2026, 9, 12))
    resume_rollback(prepared_job["id"])
    result = capture_registration.complete(prepared_job["id"], "windows-1", completed_at=datetime(2026, 9, 12))
    assert result["status"] == "succeeded"


def test_existing_package_destination_is_preserved(published):
    capture = published
    capture.ready_dir.mkdir()
    marker = capture.ready_dir / "foreign"
    marker.write_bytes(b"do-not-overwrite")
    with pytest.raises(CaptureRollbackError):
        capture.rollback()
    assert marker.read_bytes() == b"do-not-overwrite"
    assert capture.processed_package.joinpath("manifest.json").is_file()
    assert (capture.target / "001.png").read_bytes() == b"old-image"


def test_nonempty_backup_generation_is_never_recursively_deleted(published):
    capture = published
    marker = capture.backup_generation / "foreign"
    marker.write_bytes(b"preserve")
    with pytest.raises(CaptureRollbackError):
        capture.rollback()
    assert marker.read_bytes() == b"preserve"
    assert read_record(capture.job["id"]).pending.generation_pending is True
    assert (capture.target / "001.png").read_bytes() == b"old-image"


def test_metadata_conflict_does_not_overwrite_later_edits(published):
    capture = published
    update_meta_locked("comic", lambda data: data[capture.book_id].update({"view_count": 123}))
    with pytest.raises(CaptureRollbackError) as caught:
        capture.rollback()
    assert isinstance(caught.value.failures[0], ValueError)
    assert load_meta("comic")[capture.book_id]["view_count"] == 123
    assert (capture.target / "001.png").read_bytes() == b"old-image"


def test_cli_defaults_to_read_only_and_resume_is_explicit(published, capsys):
    capture = published
    with pytest.MonkeyPatch.context() as patch:
        fail_step(patch, capture, "package", OSError("package locked"))
        with pytest.raises(CaptureRollbackError):
            capture.rollback()
    before = recovery_path(capture.job["id"]).read_bytes()
    assert main([capture.job["id"]]) == 0
    assert '"archived": true' in capsys.readouterr().out
    assert recovery_path(capture.job["id"]).read_bytes() == before
    assert capture.processed_package.exists()
    assert main([capture.job["id"], "--resume"]) == 0
    assert not recovery_path(capture.job["id"]).exists()


@pytest.mark.parametrize("phase", ["publishing", "resuming"])
def test_uncertain_phase_blocks_automatic_resume(published, phase):
    capture = published
    record = read_record(capture.job["id"])
    record.phase = phase
    save_record(record)
    with pytest.raises(ValueError, match="手動確認"):
        resume_rollback(capture.job["id"])
    assert (capture.backup_target / "001.png").read_bytes() == b"old-image"
    assert capture.processed_package.exists()


@pytest.mark.parametrize("mismatch", ["path", "identity", "succeeded", "snapshot"])
def test_recovery_mismatch_is_rejected_before_asset_changes(published, mismatch):
    capture = published
    record = capture.recovery_record("recovery")
    if mismatch == "path":
        record.paths["target"] = str(capture.target.parent)
    elif mismatch == "identity":
        record.job.asin = "wrong-asin"
    elif mismatch == "succeeded":
        with with_db() as conn:
            conn.execute("UPDATE capture_jobs SET status='succeeded' WHERE id=?", (capture.job["id"],))
    save_record(record)
    if mismatch == "snapshot":
        payload = record.model_dump(mode="json")
        payload["metadata"] = {"previous_entry": {"authors": 123}, "applied_entry": None}
        recovery_path(capture.job["id"]).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        resume_rollback(capture.job["id"])
    assert (capture.backup_target / "001.png").read_bytes() == b"old-image"
    assert capture.processed_package.exists()


def test_failed_job_can_finish_compensation_without_becoming_succeeded(published):
    capture = published
    with pytest.MonkeyPatch.context() as patch:
        fail_step(patch, capture, "package", OSError("package locked"))
        with pytest.raises(CaptureRollbackError):
            capture.rollback()
    with with_db() as conn:
        conn.execute("UPDATE capture_jobs SET status='failed' WHERE id=?", (capture.job["id"],))
    resume_rollback(capture.job["id"])
    with with_db() as conn:
        assert (
            conn.execute("SELECT status FROM capture_jobs WHERE id=?", (capture.job["id"],)).fetchone()[0] == "failed"
        )


def test_record_write_failure_keeps_initial_marker_and_reports_snapshot(published, monkeypatch):
    capture = published

    def fail(_record) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr(capture_publication, "save_record", fail)
    with pytest.raises(CaptureRollbackError) as caught:
        capture.rollback(original=RuntimeError("original failure"))
    assert (capture.target / "001.png").read_bytes() == b"old-image"
    assert read_record(capture.job["id"]).phase == "publishing"
    assert "Recovery state not persisted:" in caught.value.failures[-1].__notes__[0]
    assert "original failure" in caught.value.failures[-1].__notes__[0]
