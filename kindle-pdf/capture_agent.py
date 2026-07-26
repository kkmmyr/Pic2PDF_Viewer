"""Linux管理のKindle capture jobを自動実行するWindows agent。"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from capture_agent_transport import (
    AgentConfig,
    AgentExecutionError,
    ApiClient,
    HeartbeatWorker,
)
from capture_package import (
    package_path as _package_path,
    publish_package as _publish_package,
    safe_capture_title as _safe_capture_title,
)
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

_COMPATIBILITY_EXPORTS = (_package_path,)


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
        source=job["source"],
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
