import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path

from capture_agent_transport import AgentConfig, AgentExecutionError

_READY_RENAME_RETRY_DELAYS = (0.5, 1.0, 2.0, 4.0)


def safe_capture_title(job: dict) -> str:
    identity = job.get("identity") or {}
    title = str(identity.get("title") or job.get("title") or job["asin"])
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip().rstrip(".")
    if not cleaned:
        raise AgentExecutionError(
            "book_identity_unverified",
            "書籍タイトルを安全な保存名へ変換できません",
        )
    return cleaned[:180]


def package_path(inbox: Path, job_id: str, suffix: str) -> Path:
    root = inbox.resolve()
    target = (root / f"{job_id}.{suffix}").resolve()
    if not target.is_relative_to(root):
        raise AgentExecutionError("transfer_failed", "capture packageのパスが不正です")
    return target


def _promote_ready(partial: Path, ready: Path) -> None:
    for retry, delay in enumerate((0.0, *_READY_RENAME_RETRY_DELAYS)):
        if retry:
            time.sleep(delay)
        try:
            os.replace(partial, ready)
            return
        except PermissionError:
            if retry == len(_READY_RENAME_RETRY_DELAYS):
                raise


def publish_package(config: AgentConfig, job: dict, image_dir: Path) -> Path:
    job_id = job["id"]
    partial = package_path(config.inbox, job_id, "partial")
    ready = package_path(config.inbox, job_id, "ready")
    config.inbox.mkdir(parents=True, exist_ok=True)
    if partial.exists():
        if partial.is_symlink() or not partial.is_dir():
            raise AgentExecutionError(
                "transfer_failed",
                "既存の.partial packageが安全なディレクトリではありません",
            )
        shutil.rmtree(partial)
    if ready.exists():
        raise AgentExecutionError(
            "transfer_failed",
            "同じジョブの.ready packageが既にあります",
        )
    try:
        images = partial / "images"
        images.mkdir(parents=True)
        manifest_files: list[dict[str, str]] = []
        for source in sorted(
            image_dir.iterdir(),
            key=lambda path: path.name.casefold(),
        ):
            if source.suffix.casefold() not in {".png", ".jpg", ".jpeg", ".webp"}:
                continue
            target = images / source.name
            shutil.copy2(source, target)
            manifest_files.append(
                {
                    "name": source.name,
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                }
            )
        if not manifest_files:
            raise AgentExecutionError("transfer_failed", "キャプチャ画像がありません")
        manifest = {
            "job_id": job_id,
            "asin": job["asin"],
            "source": job["source"],
            "files": manifest_files,
        }
        (partial / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _promote_ready(partial, ready)
        return ready
    except Exception:
        if partial.is_dir() and not partial.is_symlink():
            shutil.rmtree(partial)
        raise
