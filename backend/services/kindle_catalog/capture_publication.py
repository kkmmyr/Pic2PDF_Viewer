"""検証済みcapture packageの外部資産公開と逆順補償。"""

import os
import shutil
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import config
from config import get_dirs_by_source
from services.kindle_catalog.capture_package_validator import safe_title
from services.meta_store import load_meta, update_meta_locked


@dataclass
class CapturePublication:
    job: dict
    ready_dir: Path
    completed_at: datetime
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
    previous_meta_entry: dict | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.title = safe_title(self.job["title"])
        self.book_id = f"{self.title}.pdf"
        self.target_base = Path(get_dirs_by_source(self.job["source"])["img"]).resolve()
        self.target_base.mkdir(parents=True, exist_ok=True)
        self.target = (self.target_base / self.title).resolve()
        if not self.target.is_relative_to(self.target_base):
            raise ValueError("正式配置先が不正です")
        self.replacing_existing = self.target.exists()
        self._validate_replacement()
        self.staging = self.target_base / f".{self.job['id']}.partial"
        processed_dir = self.ready_dir.parent / "processed"
        self.processed_package = processed_dir / self.job["id"]
        self.backup_generation = (
            Path(config.DATA_DIR).resolve()
            / ".capture-replacement-backup"
            / f"{self.completed_at:%Y%m%d-%H%M%S}_{self.job['id'][:8]}"
        )
        self.backup_target = (self.backup_generation / f"{self.job['source']}-{self.title}").resolve()
        if not self.backup_target.is_relative_to(self.backup_generation.resolve()):
            raise ValueError("既存画像の退避先が不正です")

    def _validate_replacement(self) -> None:
        if not self.replacing_existing:
            return
        existing_meta = load_meta(self.job["source"]).get(self.book_id)
        if existing_meta is None or existing_meta.get("asin") != self.job["asin"]:
            raise ValueError("同名の別書籍が既にあるため置換できません")

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
        def _apply(data: dict) -> None:
            self.previous_meta_entry = deepcopy(data.get(self.book_id))
            entry = data.setdefault(self.book_id, {"authors": []})
            entry["asin"] = self.job["asin"]

        update_meta_locked(self.job["source"], _apply)
        self.meta_updated = True

    def archive_package(self) -> None:
        self.processed_package.parent.mkdir(parents=True, exist_ok=True)
        if self.processed_package.exists():
            raise ValueError("同じジョブの処理済み package が既にあります")
        os.replace(self.ready_dir, self.processed_package)
        self.archived = True

    def rollback(self) -> None:
        if self.meta_updated:
            self._restore_meta()
        if self.archived and self.processed_package.exists() and not self.ready_dir.exists():
            os.replace(self.processed_package, self.ready_dir)
        if self.staging.is_dir():
            shutil.rmtree(self.staging)
        if self.target_published and self.target.is_dir():
            shutil.rmtree(self.target)
        if self.existing_backed_up and self.backup_target.is_dir():
            os.replace(self.backup_target, self.target)
        if self.backup_generation.is_dir():
            shutil.rmtree(self.backup_generation, ignore_errors=True)

    def _restore_meta(self) -> None:
        def _restore(data: dict) -> None:
            if self.previous_meta_entry is None:
                data.pop(self.book_id, None)
            else:
                data[self.book_id] = self.previous_meta_entry

        update_meta_locked(self.job["source"], _restore)
