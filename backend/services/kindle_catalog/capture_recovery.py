"""復旧記録と現行jobを照合し、未完了の補償だけを再開する。"""

from services.kindle_catalog.capture_publication import CapturePublication
from services.kindle_catalog.capture_recovery_record import CaptureIdentity, read_record, recovery_lock
from services.kindle_catalog.capture_registration_repository import load_recovery_job


def resume_rollback(job_id: str) -> None:
    with recovery_lock(job_id):
        _resume_locked(job_id)


def _resume_locked(job_id: str) -> None:
    record = read_record(job_id)
    if record.phase != "recovery":
        raise ValueError("公開・復旧途中で終了した記録です。資産とDBを手動確認してください")
    job = load_recovery_job(job_id)
    identity = CaptureIdentity.model_validate({name: job.get(name) for name in CaptureIdentity.model_fields})
    if identity != record.job:
        raise ValueError("復旧記録と現在のjobが一致しません")
    publication = CapturePublication.from_recovery(record)
    publication.rollback()
