"""撮影復旧記録の型、排他的な開始marker、永続化。"""

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictBool

import config
from services.library.capture_metadata import CaptureMetadataSnapshot
from utils.atomic_json import atomic_write_json
from utils.path_utils import resolve_under_base, validate_safe_name


class CaptureIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    asin: str
    source: Literal["doujin", "comic", "novel"]
    agent_id: str | None = None


class PendingCompensation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meta_updated: StrictBool
    archived: StrictBool
    staging_pending: StrictBool
    target_published: StrictBool
    existing_backed_up: StrictBool
    generation_pending: StrictBool


class RecoveryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    phase: Literal["publishing", "resuming", "recovery"]
    job: CaptureIdentity
    completed_at: datetime
    paths: dict[str, str]
    pending: PendingCompensation
    metadata: CaptureMetadataSnapshot
    registration_failure: str | None = None
    failures: list[str] = []


class CaptureRollbackError(RuntimeError):
    def __init__(self, job_id: str, path: Path, failures: list[Exception]) -> None:
        super().__init__(f"撮影補償が未完了です: job={job_id}, recovery={path}")
        self.failures = failures
        self.recovery_path = path


def recovery_root() -> Path:
    return Path(resolve_under_base(config.DATA_DIR, ".capture-recovery"))


def recovery_path(job_id: str) -> Path:
    validate_safe_name(job_id, "job_id")
    return Path(resolve_under_base(recovery_root(), f"{job_id}.json"))


def require_no_pending_recovery() -> None:
    records = sorted([*recovery_root().glob("*.json"), *recovery_root().glob("*.lock")])
    if records:
        raise RuntimeError(f"撮影復旧記録を確認してください: {records[0]}")


def begin_record(record: RecoveryRecord) -> None:
    path = recovery_path(record.job.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    # A partial marker still blocks publication after an interrupted write.
    with path.open("x", encoding="utf-8") as file:
        file.write(record.model_dump_json(indent=2))
        file.flush()
        os.fsync(file.fileno())


def save_record(record: RecoveryRecord) -> None:
    atomic_write_json(recovery_path(record.job.id), record.model_dump(mode="json"))


def read_record(job_id: str) -> RecoveryRecord:
    record = RecoveryRecord.model_validate(json.loads(recovery_path(job_id).read_text(encoding="utf-8")))
    if record.job.id != job_id:
        raise ValueError("復旧記録のjob IDが一致しません")
    return record


def clear_record(job_id: str) -> None:
    recovery_path(job_id).unlink(missing_ok=True)


@contextmanager
def recovery_lock(job_id: str) -> Iterator[None]:
    path = recovery_path(job_id).with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    # A crash leaves this lock for manual inspection; never steal it by age.
    with path.open("x", encoding="utf-8"):
        pass
    try:
        yield
    except Exception as original:
        try:
            path.unlink()
        except OSError as cleanup:
            raise ExceptionGroup("Capture recovery and lock cleanup failures", [original, cleanup]) from None
        raise
    else:
        path.unlink()
