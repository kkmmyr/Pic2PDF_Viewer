"""検証済みcapture packageの正式配置と補償処理。"""

import os
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import config
from config import get_dirs_by_source
from services.kindle_catalog.capture_job_repository import row_dict
from services.kindle_catalog.capture_package_validator import (
    safe_title,
    validate_ready_dir,
)
from services.kindle_catalog.connection import with_db
from services.meta_store import load_meta, update_meta_locked


def _inject_failure(_point: str) -> None:
    """障害注入テスト用。productionでは何もしない。"""


def complete(
    job_id: str,
    agent_id: str,
    *,
    completed_at: datetime,
) -> dict:
    """`<job_id>.ready`を検証し、正式領域へatomic publishする。"""
    inbox = Path(config.KINDLE_CAPTURE_INBOX_DIR)
    ready_dir = inbox / f"{job_id}.ready"
    with with_db() as conn:
        row = conn.execute(
            """
            SELECT cj.*, b.title
            FROM capture_jobs cj JOIN books b ON b.asin=cj.asin
            WHERE cj.id=?
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            raise ValueError("キャプチャジョブが見つかりません")
        job = row_dict(row)
    if job["agent_id"] != agent_id or job["status"] != "awaiting_files":
        raise ValueError("完了報告できるジョブ状態ではありません")
    _manifest, files = validate_ready_dir(job, ready_dir)

    title = safe_title(job["title"])
    book_id = f"{title}.pdf"
    target_base = Path(get_dirs_by_source(job["source"])["img"]).resolve()
    target_base.mkdir(parents=True, exist_ok=True)
    target = (target_base / title).resolve()
    if not target.is_relative_to(target_base):
        raise ValueError("正式配置先が不正です")
    replacing_existing = target.exists()
    if replacing_existing:
        existing_meta = load_meta(job["source"]).get(book_id)
        if existing_meta is None or existing_meta.get("asin") != job["asin"]:
            raise ValueError("同名の別書籍が既にあるため置換できません")
    staging = target_base / f".{job_id}.partial"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    processed_dir = inbox / "processed"
    processed_package = processed_dir / job_id
    backup_generation = (
        Path(config.DATA_DIR).resolve() / ".capture-replacement-backup" / f"{completed_at:%Y%m%d-%H%M%S}_{job_id[:8]}"
    )
    backup_target = (backup_generation / f"{job['source']}-{title}").resolve()
    if not backup_target.is_relative_to(backup_generation.resolve()):
        raise ValueError("既存画像の退避先が不正です")
    archived = False
    existing_backed_up = False
    meta_updated = False
    previous_meta_entry: dict | None = None
    try:
        for source_file in files:
            shutil.copy2(source_file, staging / source_file.name)
        if replacing_existing:
            backup_generation.mkdir(parents=True, exist_ok=False)
            os.replace(target, backup_target)
            existing_backed_up = True
            _inject_failure("after_existing_backup")
        os.replace(staging, target)
        _inject_failure("after_target_publish")

        def _apply(data):
            nonlocal previous_meta_entry
            previous_meta_entry = deepcopy(data.get(book_id))
            entry = data.setdefault(book_id, {"authors": []})
            entry["asin"] = job["asin"]

        update_meta_locked(job["source"], _apply)
        meta_updated = True
        _inject_failure("after_meta_update")

        processed_dir.mkdir(parents=True, exist_ok=True)
        if processed_package.exists():
            raise ValueError("同じジョブの処理済み package が既にあります")
        os.replace(ready_dir, processed_package)
        archived = True
        _inject_failure("after_package_archive")
        _inject_failure("before_job_update")

        with with_db() as conn:
            completed_value = completed_at.isoformat()
            updated = conn.execute(
                """
                UPDATE capture_jobs SET
                    status='succeeded',completed_at=?,heartbeat_at=?,
                    book_id=?,captured_screens=?
                WHERE id=? AND status='awaiting_files' AND agent_id=?
                """,
                (
                    completed_value,
                    completed_value,
                    book_id,
                    len(files),
                    job_id,
                    agent_id,
                ),
            ).rowcount
            if updated != 1:
                raise ValueError("キャプチャジョブの完了更新に失敗しました")
    except Exception:
        if meta_updated:

            def _restore(data):
                if previous_meta_entry is None:
                    data.pop(book_id, None)
                else:
                    data[book_id] = previous_meta_entry

            update_meta_locked(job["source"], _restore)
        if archived and processed_package.exists() and not ready_dir.exists():
            os.replace(processed_package, ready_dir)
        if staging.is_dir():
            shutil.rmtree(staging)
        if target.is_dir():
            shutil.rmtree(target)
        if existing_backed_up and backup_target.is_dir():
            os.replace(backup_target, target)
            shutil.rmtree(backup_generation, ignore_errors=True)
        raise
    return {
        "job_id": job_id,
        "status": "succeeded",
        "source": job["source"],
        "book_id": book_id,
        "captured_screens": len(files),
    }
