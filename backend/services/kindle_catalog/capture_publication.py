"""検証済みcapture packageの外部資産公開と逆順補償。"""

import os
import shutil
from dataclasses import InitVar, dataclass, field
from datetime import datetime
from pathlib import Path

import config
from config import get_dirs_by_source
from services.kindle_catalog.capture_package_validator import safe_title
from services.kindle_catalog.capture_recovery_record import (
    CaptureIdentity,
    CaptureRollbackError,
    PendingCompensation,
    RecoveryRecord,
    begin_record,
    clear_record,
    recovery_path,
    save_record,
)
from services.library.capture_metadata import CaptureMetadataChange, validate_capture_replacement
from utils.path_utils import resolve_under_base, validate_safe_name


@dataclass
class CapturePublication:
    job: dict
    ready_dir: Path
    completed_at: datetime
    validate_existing: InitVar[bool] = True
    title: str = field(init=False)
    book_id: str = field(init=False)
    target_base: Path = field(init=False)
    target: Path = field(init=False)
    staging: Path = field(init=False)
    processed_package: Path = field(init=False)
    backup_generation: Path = field(init=False)
    backup_target: Path = field(init=False)
    replacing_existing: bool = field(init=False)
    archived: bool = field(default=False, init=False)
    existing_backed_up: bool = field(default=False, init=False)
    target_published: bool = field(default=False, init=False)
    meta_updated: bool = field(default=False, init=False)
    staging_pending: bool = field(default=True, init=False)
    generation_pending: bool = field(default=True, init=False)
    _registration_failure: str | None = field(default=None, init=False)
    _metadata: CaptureMetadataChange = field(default_factory=CaptureMetadataChange, init=False)

    def __post_init__(self, validate_existing: bool) -> None:
        validate_safe_name(self.job["id"], "job_id")
        self.title = safe_title(self.job["title"])
        self.book_id = f"{self.title}.pdf"
        self.target_base = Path(get_dirs_by_source(self.job["source"])["img"]).resolve()
        self.target_base.mkdir(parents=True, exist_ok=True)
        self.target = (self.target_base / self.title).resolve()
        if not self.target.is_relative_to(self.target_base):
            raise ValueError("正式配置先が不正です")
        self.replacing_existing = self.target.exists()
        if validate_existing:
            self._validate_replacement()
        self.staging = Path(resolve_under_base(self.target_base, f".{self.job['id']}.partial"))
        self.processed_package = Path(resolve_under_base(self.ready_dir.parent, f"processed/{self.job['id']}"))
        self.backup_generation = Path(
            resolve_under_base(
                config.DATA_DIR,
                f".capture-replacement-backup/{self.completed_at:%Y%m%d-%H%M%S}_{self.job['id'][:8]}",
            )
        )
        self.backup_target = (self.backup_generation / f"{self.job['source']}-{self.title}").resolve()
        if not self.backup_target.is_relative_to(self.backup_generation.resolve()):
            raise ValueError("既存画像の退避先が不正です")

    def _validate_replacement(self) -> None:
        if not self.replacing_existing:
            return
        validate_capture_replacement(self.job["source"], self.book_id, self.job["asin"])

    def stage(self, files: list[Path]) -> None:
        if self.staging.exists():
            shutil.rmtree(self.staging)
        self.staging.mkdir()
        for source_file in files:
            shutil.copy2(source_file, self.staging / source_file.name)

    def backup_existing(self) -> None:
        if not self.replacing_existing:
            return
        self.backup_generation.mkdir(parents=True, exist_ok=False)
        os.replace(self.target, self.backup_target)
        self.existing_backed_up = True

    def publish_target(self) -> None:
        os.replace(self.staging, self.target)
        self.target_published = True

    def update_meta(self) -> None:
        self._metadata.apply(self.job["source"], self.book_id, self.job["asin"])
        self.meta_updated = True

    def archive_package(self) -> None:
        self.processed_package.parent.mkdir(parents=True, exist_ok=True)
        if self.processed_package.exists():
            raise ValueError("同じジョブの処理済み package が既にあります")
        os.replace(self.ready_dir, self.processed_package)
        self.archived = True

    def rollback(self, *, original: Exception | None = None) -> None:
        if original is not None:
            self._registration_failure = f"{type(original).__name__}: {original}"
        failures: list[Exception] = []
        try:
            save_record(self.recovery_record("resuming"))
        except Exception as error:
            error.add_note("復旧開始状態の保存に失敗")
            failures.append(error)
        steps = (
            ("meta_updated", self._restore_meta),
            ("archived", self._restore_package),
            ("staging_pending", lambda: self._remove_directory(self.staging)),
            ("target_published", lambda: self._remove_directory(self.target)),
            ("existing_backed_up", self._restore_backup),
            ("generation_pending", self._remove_generation),
        )
        for flag, restore in steps:
            if not getattr(self, flag):
                continue
            try:
                restore()
                setattr(self, flag, False)
            except Exception as error:
                error.add_note(f"Capture compensation failed: {flag}, job={self.job['id']}, paths={self._paths()}")
                failures.append(error)
        if not failures:
            try:
                self.clear_recovery()
            except Exception as error:
                failures.append(error)
        if failures:
            self._raise_recovery_error(failures)

    def _raise_recovery_error(self, failures: list[Exception]) -> None:
        record = self.recovery_record("recovery")
        record.failures = [
            f"{type(error).__name__}: {error}; {'; '.join(getattr(error, '__notes__', []))}" for error in failures
        ]
        try:
            save_record(record)
        except Exception as error:
            error.add_note(f"Recovery state not persisted: {record.model_dump_json()}")
            failures.append(error)
        recovery_error = CaptureRollbackError(self.job["id"], recovery_path(self.job["id"]), failures)
        raise recovery_error from ExceptionGroup("Capture compensation failures", failures)

    def _restore_package(self) -> None:
        if self.ready_dir.exists() or self.ready_dir.is_symlink():
            raise FileExistsError(f"package復元先に既存資産があります: {self.ready_dir}")
        os.replace(self.processed_package, self.ready_dir)

    @staticmethod
    def _remove_directory(path: Path) -> None:
        if path.is_symlink():
            raise ValueError(f"symlinkを削除対象にできません: {path}")
        if path.exists():
            shutil.rmtree(path)

    def _restore_backup(self) -> None:
        if self.target_published or self.target.exists():
            raise FileExistsError(f"旧画像の復元先が空いていません: {self.target}")
        os.replace(self.backup_target, self.target)

    def _remove_generation(self) -> None:
        if self.existing_backed_up:
            raise RuntimeError(f"旧画像が未復元のため退避世代を保持します: {self.backup_generation}")
        if self.backup_generation.exists():
            self.backup_generation.rmdir()

    def _restore_meta(self) -> None:
        self._metadata.restore(self.job["source"], self.book_id)

    def _paths(self) -> dict[str, str]:
        return {
            name: str(getattr(self, name).absolute())
            for name in ("ready_dir", "target", "staging", "processed_package", "backup_generation", "backup_target")
        }

    def recovery_record(self, phase: str) -> RecoveryRecord:
        return RecoveryRecord.model_validate(
            {
                "phase": phase,
                "job": {name: self.job.get(name) for name in CaptureIdentity.model_fields},
                "completed_at": self.completed_at,
                "paths": self._paths(),
                "pending": {name: getattr(self, name) for name in PendingCompensation.model_fields},
                "metadata": self._metadata.snapshot(),
                "registration_failure": self._registration_failure,
            }
        )

    def begin(self) -> None:
        begin_record(self.recovery_record("publishing"))

    def clear_recovery(self) -> None:
        clear_record(self.job["id"])

    @classmethod
    def from_recovery(cls, record: RecoveryRecord) -> "CapturePublication":
        capture = cls(
            record.job.model_dump(),
            Path(config.KINDLE_CAPTURE_INBOX_DIR) / f"{record.job.id}.ready",
            record.completed_at,
            validate_existing=False,
        )
        if capture._paths() != record.paths:
            raise ValueError("復旧記録と現在の保存先が一致しません")
        capture._metadata = CaptureMetadataChange.from_snapshot(record.metadata)
        if record.pending.meta_updated and capture._metadata.applied_entry is None:
            raise ValueError("更新後メタsnapshotがありません")
        capture._registration_failure = record.registration_failure
        for name, pending in record.pending.model_dump().items():
            setattr(capture, name, pending)
        return capture
