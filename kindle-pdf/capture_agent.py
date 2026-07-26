"""Linux管理のKindle capture jobを自動実行するWindows agent。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from capturer import AutoKindleCapturer
from kindle_app_controller import (
    BookIdentity,
    ControllerConfig,
    KindleAppController,
    KindleControllerError,
)
from novel_capturer import NovelKindleCapturer

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass


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
        self.positioning_timeout_seconds = max(
            1, int(os.environ.get("KINDLE_POSITIONING_TIMEOUT_SECONDS", "3600"))
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


def _safe_capture_title(job: dict) -> str:
    identity = job.get("identity") or {}
    title = str(identity.get("title") or job.get("title") or job["asin"])
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip().rstrip(".")
    if not cleaned:
        raise AgentExecutionError(
            "book_identity_unverified",
            "書籍タイトルを安全な保存名へ変換できません",
        )
    return cleaned[:180]


def _capture(
    job: dict,
    output_root: Path,
    on_page,
    *,
    reading_area_bounds_provider,
) -> tuple[int, Path]:
    capturer = (
        NovelKindleCapturer() if job["source"] == "novel" else AutoKindleCapturer()
    )
    capturer.config.IMG_OUTPUT_DIR = str(output_root)
    capturer.config.PAGE_CHANGE_KEY = job["direction"]
    capturer.config.EXPECTED_PAGES = job.get("expected_screens")
    capturer.config.CAPTURE_SPREAD = job["source"] == "comic"
    if not capturer.find_window():
        raise AgentExecutionError(
            "kindle_app_exited",
            "撮影開始時にKindleウィンドウが見つかりません",
        )
    try:
        capturer.setup_window(
            reading_area_bounds_provider=reading_area_bounds_provider,
        )
        page_count, image_dir = capturer.capture_loop(
            _safe_capture_title(job),
            on_page=on_page,
        )
        if page_count <= 0:
            raise AgentExecutionError("capture_failed", "キャプチャ画像がありません")
        return page_count, Path(image_dir)
    finally:
        capturer.cleanup()


def _package_path(inbox: Path, job_id: str, suffix: str) -> Path:
    root = inbox.resolve()
    target = (root / f"{job_id}.{suffix}").resolve()
    if not target.is_relative_to(root):
        raise AgentExecutionError("transfer_failed", "capture packageのパスが不正です")
    return target


def _publish_package(config: AgentConfig, job: dict, image_dir: Path) -> Path:
    job_id = job["id"]
    partial = _package_path(config.inbox, job_id, "partial")
    ready = _package_path(config.inbox, job_id, "ready")
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
        os.replace(partial, ready)
        return ready
    except Exception:
        if partial.is_dir() and not partial.is_symlink():
            shutil.rmtree(partial)
        raise


def _state(
    api: ApiClient,
    job_id: str,
    agent_id: str,
    state: str,
    **extra,
) -> dict:
    return api.post(
        f"/api/kindle-catalog/agents/jobs/{job_id}/state",
        {"agent_id": agent_id, "state": state, **extra},
    )


def _complete(api: ApiClient, job_id: str, agent_id: str) -> None:
    try:
        api.post(
            f"/api/kindle-catalog/agents/jobs/{job_id}/complete",
            {"agent_id": agent_id},
        )
    except Exception as exc:
        raise AgentExecutionError(
            "registration_failed",
            f"Pic2PDFViewerへの登録に失敗しました: {exc}",
        ) from exc


def _fail_job(
    api: ApiClient,
    job_id: str,
    agent_id: str,
    error_code: str,
    message: str,
) -> None:
    _state(
        api,
        job_id,
        agent_id,
        "failed",
        error_code=error_code,
        error_message=message[:1000],
    )


def _run_claimed_job(
    config: AgentConfig,
    api: ApiClient,
    job: dict,
    controller: KindleAppController,
    heartbeat: HeartbeatWorker,
) -> None:
    job_id = job["id"]
    identity = BookIdentity.from_job(job)

    _state(api, job_id, config.agent_id, "locating_book")
    controller.attach_running_app()
    candidate = controller.search_book(identity)
    heartbeat.raise_if_failed()

    if controller.needs_download(candidate):
        _state(api, job_id, config.agent_id, "downloading")
        controller.wait_for_download(
            candidate,
            on_poll=heartbeat.raise_if_failed,
        )
        candidate = controller.search_book(identity)

    _state(api, job_id, config.agent_id, "positioning")
    controller.open_book(candidate)
    controller.set_page_layout(job["source"])
    controller.go_to_start(
        direction=job["direction"],
        on_poll=heartbeat.raise_if_failed,
    )
    heartbeat.raise_if_failed()

    _state(api, job_id, config.agent_id, "capturing")

    def on_page(page: int) -> None:
        heartbeat.raise_if_failed()
        if page == 1 or page % 5 == 0:
            _state(
                api,
                job_id,
                config.agent_id,
                "capturing",
                captured_screens=page,
            )

    try:
        with tempfile.TemporaryDirectory(prefix=f"kindle-{job_id}-") as temp:
            page_count, image_dir = _capture(
                job,
                Path(temp),
                on_page,
                reading_area_bounds_provider=lambda: controller.capture_area_bounds(
                    job["source"]
                ),
            )
            heartbeat.raise_if_failed()
            try:
                _publish_package(config, job, image_dir)
            except AgentExecutionError:
                raise
            except Exception as exc:
                raise AgentExecutionError(
                    "transfer_failed",
                    f"capture packageの転送に失敗しました: {exc}",
                ) from exc
    except AgentExecutionError:
        raise
    except Exception as exc:
        raise AgentExecutionError(
            "capture_failed",
            f"Kindle撮影に失敗しました: {exc}",
        ) from exc

    _state(
        api,
        job_id,
        config.agent_id,
        "awaiting_files",
        captured_screens=page_count,
    )
    _complete(api, job_id, config.agent_id)


def run_once(
    config: AgentConfig,
    api: ApiClient,
    *,
    controller_factory=KindleAppController,
) -> bool:
    response = api.post(
        "/api/kindle-catalog/agents/claim",
        {"agent_id": config.agent_id},
    )
    job = response.get("job")
    if not job:
        return False

    job_id = job["id"]
    current_state = job["status"]
    heartbeat = HeartbeatWorker(
        api,
        job_id,
        config.agent_id,
        config.heartbeat_seconds,
    )
    heartbeat.start()
    try:
        if current_state == "awaiting_files":
            _complete(api, job_id, config.agent_id)
            return True
        if current_state != "claimed":
            raise AgentExecutionError(
                "agent_restart_requires_new_job",
                "途中状態のジョブは自動再開せず、新しいジョブとして再実行してください",
            )
        controller = controller_factory(
            ControllerConfig(
                download_timeout_seconds=config.download_timeout_seconds,
                positioning_timeout_seconds=config.positioning_timeout_seconds,
            )
        )
        _run_claimed_job(config, api, job, controller, heartbeat)
        return True
    except KindleControllerError as exc:
        _fail_job(api, job_id, config.agent_id, exc.error_code, str(exc))
        return True
    except AgentExecutionError as exc:
        _fail_job(api, job_id, config.agent_id, exc.error_code, str(exc))
        return True
    except Exception as exc:
        _fail_job(
            api,
            job_id,
            config.agent_id,
            "capture_failed",
            str(exc),
        )
        return True
    finally:
        heartbeat.stop()


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
