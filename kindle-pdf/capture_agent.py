"""Linux 管理の Kindle キャプチャジョブを実行する Windows エージェント。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import tempfile
import time
import tkinter as tk
import urllib.error
import urllib.request
from pathlib import Path
from tkinter import messagebox

from capturer import AutoKindleCapturer
from novel_capturer import NovelKindleCapturer

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass


class AgentConfig:
    def __init__(self) -> None:
        self.api_url = os.environ.get(
            "PIC2PDF_API_URL", "http://medaroserver:8090"
        ).rstrip("/")
        self.token = os.environ.get("KINDLE_CAPTURE_AGENT_TOKEN", "")
        inbox_value = os.environ.get("KINDLE_CAPTURE_INBOX_DIR", "")
        self.inbox = Path(inbox_value) if inbox_value else Path()
        self.agent_id = os.environ.get("KINDLE_CAPTURE_AGENT_ID", socket.gethostname())
        self.poll_seconds = max(
            2, int(os.environ.get("KINDLE_CAPTURE_POLL_SECONDS", "10"))
        )
        if not self.token:
            raise RuntimeError("KINDLE_CAPTURE_AGENT_TOKEN が設定されていません")
        if not inbox_value:
            raise RuntimeError("KINDLE_CAPTURE_INBOX_DIR が設定されていません")


class ApiClient:
    def __init__(self, config: AgentConfig) -> None:
        self.config = config

    def post(self, path: str, body: dict) -> dict:
        request = urllib.request.Request(
            f"{self.config.api_url}{path}",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Capture-Agent-Token": self.config.token,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"API {exc.code}: {detail}") from exc


def _confirm_book(title: str, source: str) -> bool:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return messagebox.askokcancel(
            "Kindle キャプチャ",
            f"Kindle アプリで次の書籍を開いてください。\n\n{title}\n\n"
            f"種別: {source}\n準備できたら OK を押してください。",
            parent=root,
        )
    finally:
        root.destroy()


def _capture(job: dict, output_root: Path) -> tuple[int, Path]:
    capturer = (
        NovelKindleCapturer() if job["source"] == "novel" else AutoKindleCapturer()
    )
    capturer.config.IMG_OUTPUT_DIR = str(output_root)
    capturer.config.PAGE_CHANGE_KEY = job["direction"]
    capturer.config.EXPECTED_PAGES = job.get("expected_screens")
    if not capturer.find_window():
        raise RuntimeError("Kindle ウィンドウが見つかりません")
    try:
        capturer.setup_window()
        page_count, image_dir = capturer.capture_loop(job["title"])
        return page_count, Path(image_dir)
    finally:
        capturer.cleanup()


def _publish_package(config: AgentConfig, job: dict, image_dir: Path) -> Path:
    job_id = job["id"]
    partial = config.inbox / f"{job_id}.partial"
    ready = config.inbox / f"{job_id}.ready"
    config.inbox.mkdir(parents=True, exist_ok=True)
    if partial.exists():
        shutil.rmtree(partial)
    if ready.exists():
        raise RuntimeError("同じジョブの .ready package が既にあります")
    images = partial / "images"
    images.mkdir(parents=True)
    manifest_files: list[dict[str, str]] = []
    for source in sorted(image_dir.iterdir(), key=lambda path: path.name.casefold()):
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
        raise RuntimeError("キャプチャ画像がありません")
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
    os.replace(partial, ready)
    return ready


def _state(api: ApiClient, job_id: str, agent_id: str, state: str, **extra) -> dict:
    return api.post(
        f"/api/kindle-catalog/agents/jobs/{job_id}/state",
        {"agent_id": agent_id, "state": state, **extra},
    )


def run_once(config: AgentConfig, api: ApiClient) -> bool:
    response = api.post(
        "/api/kindle-catalog/agents/claim",
        {"agent_id": config.agent_id},
    )
    job = response.get("job")
    if not job:
        return False
    job_id = job["id"]
    current_state = job["status"]
    try:
        if current_state == "claimed":
            _state(api, job_id, config.agent_id, "waiting_user")
            current_state = "waiting_user"
        if current_state == "waiting_user":
            if not _confirm_book(job["title"], job["source"]):
                _state(
                    api,
                    job_id,
                    config.agent_id,
                    "failed",
                    error_code="user_cancelled",
                    error_message="ユーザーがキャプチャをキャンセルしました",
                )
                return True
            _state(api, job_id, config.agent_id, "capturing")
            current_state = "capturing"
        if current_state == "awaiting_files":
            api.post(
                f"/api/kindle-catalog/agents/jobs/{job_id}/complete",
                {"agent_id": config.agent_id},
            )
            return True
        if current_state != "capturing":
            raise RuntimeError(f"再開できないジョブ状態です: {current_state}")
        with tempfile.TemporaryDirectory(prefix=f"kindle-{job_id}-") as temp:
            page_count, image_dir = _capture(job, Path(temp))
            _publish_package(config, job, image_dir)
        _state(
            api,
            job_id,
            config.agent_id,
            "awaiting_files",
            captured_screens=page_count,
        )
        api.post(
            f"/api/kindle-catalog/agents/jobs/{job_id}/complete",
            {"agent_id": config.agent_id},
        )
        return True
    except Exception as exc:
        try:
            _state(
                api,
                job_id,
                config.agent_id,
                "failed",
                error_code="agent_error",
                error_message=str(exc)[:1000],
            )
        except Exception:
            pass
        raise


def main() -> None:
    config = AgentConfig()
    api = ApiClient(config)
    print(f"Kindle capture agent: {config.agent_id}")
    print(f"API: {config.api_url}")
    print(f"Inbox: {config.inbox}")
    while True:
        try:
            handled = run_once(config, api)
            if not handled:
                time.sleep(config.poll_seconds)
        except KeyboardInterrupt:
            return
        except Exception as exc:
            print(f"Capture agent error: {exc}")
            time.sleep(config.poll_seconds)


if __name__ == "__main__":
    main()
