"""Windows OCR agent for server-owned manifests and page checkpoints."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from services.novel_db.extractor import OcrTask, iter_ocr_pages


class AgentConfig:
    def __init__(self) -> None:
        self.api_url = os.environ.get("PIC2PDF_API_URL", "http://medaroserver:8090").rstrip("/")
        self.token = os.environ.get("KINDLE_CAPTURE_AGENT_TOKEN", "")
        self.agent_id = os.environ.get("OCR_AGENT_ID", socket.gethostname())
        self.poll_seconds = max(2, int(os.environ.get("OCR_AGENT_POLL_SECONDS", "10")))
        self.heartbeat_seconds = max(5, int(os.environ.get("OCR_AGENT_HEARTBEAT_SECONDS", "30")))
        if not self.token:
            raise RuntimeError("KINDLE_CAPTURE_AGENT_TOKEN が設定されていません")


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
        return self._open_json(request)

    def get_bytes(self, path: str) -> bytes:
        request = urllib.request.Request(
            f"{self.config.api_url}{path}",
            headers={
                "X-Capture-Agent-Token": self.config.token,
                "X-OCR-Agent-ID": self.config.agent_id,
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"API {exc.code}: {detail}") from exc

    @staticmethod
    def _open_json(request: urllib.request.Request) -> dict:
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"API {exc.code}: {detail}") from exc


class HeartbeatWorker:
    def __init__(self, api: ApiClient, job_id: int, agent_id: str, interval_seconds: int) -> None:
        self.api = api
        self.job_id = job_id
        self.agent_id = agent_id
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._error: Exception | None = None
        self._thread = threading.Thread(target=self._run, name=f"ocr-heartbeat-{job_id}", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=self.interval_seconds + 1)

    def raise_if_failed(self) -> None:
        if self._error is not None:
            raise RuntimeError(f"OCR agent heartbeat failed: {self._error}")

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.api.post(
                    f"/api/ocr/agents/jobs/{self.job_id}/heartbeat",
                    {"agent_id": self.agent_id},
                )
            except Exception as exc:
                self._error = exc
                return


def _download_tasks(config: AgentConfig, api: ApiClient, job: dict, root: Path) -> list[OcrTask]:
    tasks: list[OcrTask] = []
    for book in job["books"]:
        book_dir = root / f"run-{book['run_id']}"
        book_dir.mkdir(parents=True)
        for remote_task in book["tasks"]:
            image_bytes = api.get_bytes(remote_task["image_url"])
            actual_hash = hashlib.sha256(image_bytes).hexdigest()
            if actual_hash != remote_task["image_sha256"]:
                raise RuntimeError(f"image SHA-256 mismatch: {remote_task['book_name']} page {remote_task['page_no']}")
            image_path = book_dir / f"{int(remote_task['page_no']):03}.png"
            image_path.write_bytes(image_bytes)
            tasks.append(
                {
                    "book_name": remote_task["book_name"],
                    "page_no": int(remote_task["page_no"]),
                    "image_path": str(image_path),
                }
            )
    return tasks


def run_once(config: AgentConfig, api: ApiClient | None = None) -> bool:
    api = api or ApiClient(config)
    claimed = api.post("/api/ocr/agents/claim", {"agent_id": config.agent_id})
    job = claimed.get("job")
    if job is None:
        return False

    job_id = int(job["id"])
    heartbeat = HeartbeatWorker(api, job_id, config.agent_id, config.heartbeat_seconds)
    heartbeat.start()
    try:
        with tempfile.TemporaryDirectory(prefix=f"pic2pdf-ocr-agent-{job_id}-") as temp_dir:
            tasks = _download_tasks(config, api, job, Path(temp_dir))
            for book_name, page in iter_ocr_pages(tasks):
                heartbeat.raise_if_failed()
                api.post(
                    f"/api/ocr/agents/jobs/{job_id}/pages",
                    {
                        "agent_id": config.agent_id,
                        "book_name": book_name,
                        "page": page,
                    },
                )
        heartbeat.raise_if_failed()
        api.post(
            f"/api/ocr/agents/jobs/{job_id}/complete",
            {"agent_id": config.agent_id},
        )
        return True
    except Exception as exc:
        try:
            api.post(
                f"/api/ocr/agents/jobs/{job_id}/fail",
                {"agent_id": config.agent_id, "error": str(exc)},
            )
        except Exception:
            pass
        raise
    finally:
        heartbeat.stop()


def main() -> None:
    config = AgentConfig()
    api = ApiClient(config)
    print(f"OCR agent: {config.agent_id}")
    while True:
        try:
            handled = run_once(config, api)
        except KeyboardInterrupt:
            return
        except Exception as exc:
            print(f"OCR agent error: {exc}")
            handled = False
        if not handled:
            time.sleep(config.poll_seconds)


if __name__ == "__main__":
    main()
