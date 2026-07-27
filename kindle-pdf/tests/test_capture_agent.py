from __future__ import annotations

from types import SimpleNamespace

import pytest

import capture_agent
import capture_package
from kindle_app_controller import BookCandidate, KindleControllerError


def _job(status: str = "claimed") -> dict:
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "asin": "B012345678",
        "source": "novel",
        "direction": "left",
        "expected_screens": None,
        "status": status,
        "identity": {
            "asin": "B012345678",
            "title": "対象小説",
            "title_normalized": "対象小説",
            "authors": ["著者A"],
            "series_name": "対象シリーズ",
            "volume_number": 1.0,
            "volume_label": "1",
        },
    }


def _config(tmp_path):
    return SimpleNamespace(
        inbox=tmp_path / "inbox",
        agent_id="windows-test",
        heartbeat_seconds=30,
        download_timeout_seconds=60,
    )


class _Api:
    def __init__(self, job: dict, *, fail_complete: bool = False) -> None:
        self.job = job
        self.fail_complete = fail_complete
        self.calls: list[tuple[str, dict]] = []

    def post(self, path: str, body: dict) -> dict:
        self.calls.append((path, body))
        if path.endswith("/claim"):
            return {"job": self.job}
        if path.endswith("/complete") and self.fail_complete:
            raise RuntimeError("registration unavailable")
        return {"ok": True}

    @property
    def states(self) -> list[dict]:
        return [body for path, body in self.calls if path.endswith("/state")]


class _Heartbeat:
    def __init__(self, *_args, **_kwargs) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def raise_if_failed(self) -> None:
        return None


class _Controller:
    needs_download_result = False
    search_count = 0
    layout_sources: list[str] = []
    start_sources: list[str] = []

    def __init__(self, _config) -> None:
        self.candidate = BookCandidate(
            asin="B012345678",
            title="対象小説",
            card=object(),
        )

    def attach_running_app(self) -> None:
        return None

    def search_book(self, _identity):
        type(self).search_count += 1
        return self.candidate

    def needs_download(self, _candidate) -> bool:
        return type(self).needs_download_result

    def wait_for_download(self, _candidate, *, on_poll) -> None:
        on_poll()

    def open_book(self, _candidate) -> None:
        return None

    def set_page_layout(self, source: str) -> None:
        type(self).layout_sources.append(source)

    def capture_area_bounds(self, source: str) -> tuple[int, int, int, int]:
        assert source == "novel"
        return (0, 100, 1000, 728)

    def go_to_start(self, *, source, direction, on_poll) -> None:
        type(self).start_sources.append(source)
        assert direction in {"left", "right"}
        on_poll()


@pytest.fixture(autouse=True)
def _reset_controller() -> None:
    _Controller.needs_download_result = False
    _Controller.search_count = 0
    _Controller.layout_sources = []
    _Controller.start_sources = []


def _fake_capture(
    _job,
    output_root,
    on_page,
    *,
    reading_area_bounds_provider,
):
    assert reading_area_bounds_provider() == (0, 100, 1000, 728)
    image_dir = output_root / "captured"
    image_dir.mkdir()
    for page in range(1, 6):
        (image_dir / f"{page:03d}.png").write_bytes(f"page-{page}".encode())
        on_page(page)
    return 5, image_dir


def test_run_once_executes_automatic_flow_and_reports_progress(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _Api(_job())
    monkeypatch.setattr(capture_agent, "HeartbeatWorker", _Heartbeat)
    monkeypatch.setattr(capture_agent, "_capture", _fake_capture)

    handled = capture_agent.run_once(
        _config(tmp_path),
        api,
        controller_factory=_Controller,
    )

    assert handled
    assert _Controller.layout_sources == ["novel"]
    assert _Controller.start_sources == ["novel"]
    assert [state["state"] for state in api.states] == [
        "locating_book",
        "positioning",
        "capturing",
        "capturing",
        "capturing",
        "awaiting_files",
    ]
    assert api.states[3]["captured_screens"] == 1
    assert api.states[4]["captured_screens"] == 5
    assert any(path.endswith("/complete") for path, _body in api.calls)
    assert (_config(tmp_path).inbox / f"{_job()['id']}.ready").is_dir()


def test_run_once_downloads_and_reverifies_candidate(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _Api(_job())
    _Controller.needs_download_result = True
    monkeypatch.setattr(capture_agent, "HeartbeatWorker", _Heartbeat)
    monkeypatch.setattr(capture_agent, "_capture", _fake_capture)

    capture_agent.run_once(
        _config(tmp_path),
        api,
        controller_factory=_Controller,
    )

    assert "downloading" in [state["state"] for state in api.states]
    assert _Controller.search_count == 2


def test_controller_error_is_recorded_without_capture(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingController(_Controller):
        def search_book(self, _identity):
            raise KindleControllerError("book_not_found", "対象がありません")

    api = _Api(_job())
    monkeypatch.setattr(capture_agent, "HeartbeatWorker", _Heartbeat)
    capture_called = False

    def fail_if_captured(*_args, **_kwargs):
        nonlocal capture_called
        capture_called = True
        raise AssertionError

    monkeypatch.setattr(capture_agent, "_capture", fail_if_captured)

    capture_agent.run_once(
        _config(tmp_path),
        api,
        controller_factory=FailingController,
    )

    assert not capture_called
    assert api.states[-1]["state"] == "failed"
    assert api.states[-1]["error_code"] == "book_not_found"


def test_midflight_job_is_not_implicitly_resumed(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _Api(_job("positioning"))
    monkeypatch.setattr(capture_agent, "HeartbeatWorker", _Heartbeat)

    capture_agent.run_once(
        _config(tmp_path),
        api,
        controller_factory=_Controller,
    )

    assert api.states == [
        {
            "agent_id": "windows-test",
            "state": "failed",
            "error_code": "agent_restart_requires_new_job",
            "error_message": (
                "途中状態のジョブは自動再開せず、新しいジョブとして再実行してください"
            ),
        }
    ]


def test_awaiting_files_retries_only_registration(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _Api(_job("awaiting_files"))
    monkeypatch.setattr(capture_agent, "HeartbeatWorker", _Heartbeat)

    capture_agent.run_once(
        _config(tmp_path),
        api,
        controller_factory=_Controller,
    )

    assert api.states == []
    assert any(path.endswith("/complete") for path, _body in api.calls)


def test_registration_failure_uses_distinct_error_code(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _Api(_job(), fail_complete=True)
    monkeypatch.setattr(capture_agent, "HeartbeatWorker", _Heartbeat)
    monkeypatch.setattr(capture_agent, "_capture", _fake_capture)

    capture_agent.run_once(
        _config(tmp_path),
        api,
        controller_factory=_Controller,
    )

    assert api.states[-1]["state"] == "failed"
    assert api.states[-1]["error_code"] == "registration_failed"


def test_publish_failure_removes_partial_package(tmp_path) -> None:
    config = _config(tmp_path)
    empty_images = tmp_path / "empty"
    empty_images.mkdir()

    with pytest.raises(capture_agent.AgentExecutionError) as exc:
        capture_agent._publish_package(config, _job(), empty_images)

    assert exc.value.error_code == "transfer_failed"
    assert not (config.inbox / f"{_job()['id']}.partial").exists()


def test_publish_retries_transient_ready_rename(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    images = tmp_path / "images"
    images.mkdir()
    (images / "001.png").write_bytes(b"image")
    real_replace = capture_package.os.replace
    attempts = 0

    def transient_replace(source, target):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError(5, "access denied")
        real_replace(source, target)

    monkeypatch.setattr(capture_package.os, "replace", transient_replace)
    monkeypatch.setattr(capture_package.time, "sleep", lambda _seconds: None)

    ready = capture_agent._publish_package(config, _job(), images)

    assert attempts == 3
    assert ready.is_dir()
    assert not (config.inbox / f"{_job()['id']}.partial").exists()
