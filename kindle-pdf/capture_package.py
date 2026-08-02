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


def _prepare_partial(partial: Path, ready: Path) -> Path:
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
    images = partial / "images"
    images.mkdir(parents=True)
    return images


def _copy_audited_images(
    image_dir: Path, images: Path, audited_files: tuple[dict, ...]
) -> list[dict]:
    manifest_files: list[dict] = []
    audited_by_name = {item["name"]: item for item in audited_files}
    for name in sorted(audited_by_name, key=lambda value: int(Path(value).stem)):
        source = image_dir / name
        audited = audited_by_name[name]
        target = images / source.name
        shutil.copy2(source, target)
        actual_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual_hash != audited["sha256"]:
            raise AgentExecutionError(
                "transfer_failed",
                f"QA後に撮影画像が変化しました: {source.name}",
            )
        manifest_files.append(
            {
                "name": source.name,
                "sha256": actual_hash,
                "width": audited["width"],
                "height": audited["height"],
                "size": audited["size"],
            }
        )
    if not manifest_files:
        raise AgentExecutionError("transfer_failed", "キャプチャ画像がありません")
    return manifest_files


def publish_package(
    config: AgentConfig,
    job: dict,
    image_dir: Path,
    *,
    capture_report: dict | None = None,
    quality_report: dict | None = None,
    audited_files: tuple[dict, ...] | None = None,
) -> Path:
    if capture_report is None or quality_report is None or audited_files is None:
        raise AgentExecutionError(
            "transfer_failed",
            "撮影完了証跡または登録前画像QAがありません",
        )
    canary = capture_report.get("canary")
    if not isinstance(canary, dict) or canary.get("passed") is not True:
        raise AgentExecutionError(
            "transfer_failed",
            "合格した撮影前カナリア証跡がありません",
        )
    job_id = job["id"]
    partial = package_path(config.inbox, job_id, "partial")
    ready = package_path(config.inbox, job_id, "ready")
    config.inbox.mkdir(parents=True, exist_ok=True)
    try:
        images = _prepare_partial(partial, ready)
        manifest_files = _copy_audited_images(image_dir, images, audited_files)
        manifest = {
            "manifest_version": 2,
            "job_id": job_id,
            "asin": job["asin"],
            "source": job["source"],
            "capture": capture_report,
            "quality": quality_report,
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
