import json
import os
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path


class AgentExecutionError(RuntimeError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


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
        self.heartbeat_seconds = max(
            5, int(os.environ.get("KINDLE_CAPTURE_HEARTBEAT_SECONDS", "30"))
        )
        self.download_timeout_seconds = max(
            1, int(os.environ.get("KINDLE_DOWNLOAD_TIMEOUT_SECONDS", "1800"))
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


class HeartbeatWorker:
    def __init__(
        self,
        api: ApiClient,
        job_id: str,
        agent_id: str,
        interval_seconds: int,
    ) -> None:
        self.api = api
        self.job_id = job_id
        self.agent_id = agent_id
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._error: Exception | None = None
        self._thread = threading.Thread(
            target=self._run,
            name=f"kindle-heartbeat-{job_id[:8]}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=max(1, self.interval_seconds + 1))

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.api.post(
                    f"/api/kindle-catalog/agents/jobs/{self.job_id}/heartbeat",
                    {"agent_id": self.agent_id},
                )
            except Exception as exc:
                self._error = exc
                return

    def raise_if_failed(self) -> None:
        if self._error is not None:
            raise AgentExecutionError(
                "capture_failed",
                f"heartbeatの送信に失敗しました: {self._error}",
            )
