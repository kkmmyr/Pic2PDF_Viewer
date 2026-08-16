from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image

from services.novel_db import ocr_worker
from services.novel_db.surya_types import SuryaBlock, SuryaPageResult


def _passed_result() -> SuryaPageResult:
    return SuryaPageResult(
        full_text="本文",
        raw_output='<div data-label="Text" data-bbox="0 0 1000 1000">本文</div>',
        blocks=[SuryaBlock("Text", (0, 0, 1000, 1000), "本文")],
        state="passed",
        quality_flags=[],
        ink_coverage=1.0,
        attempt_count=1,
    )


def _configure_session_policy(monkeypatch, *, max_pages: int) -> None:
    monkeypatch.setenv("SURYA_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("OCR_SERVER_MAX_PAGES", str(max_pages))
    monkeypatch.setenv("OCR_SERVER_CONSECUTIVE_FAILURES", "2")
    monkeypatch.setenv("OCR_SERVER_FAILURE_WINDOW", "4")
    monkeypatch.setenv("OCR_SERVER_FAILURE_RATE", "0.5")
    monkeypatch.setenv("OCR_CROSSCHECK_ALL_PAGES", "false")


def test_worker_restarts_owned_server_at_page_limit_without_duplicate_results(
    monkeypatch,
    capsys,
) -> None:
    servers: list[object] = []

    class FakeServer:
        owns_process = True

        def __init__(self, *_args, **_kwargs) -> None:
            servers.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    class FakeClient:
        min_ink_coverage = 0.85

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def recognize_with_quality(self, _image, *, max_attempts):
            assert max_attempts == 1
            return _passed_result()

    monkeypatch.setattr(ocr_worker, "SuryaServer", FakeServer)
    monkeypatch.setattr(ocr_worker, "SuryaClient", FakeClient)
    monkeypatch.setattr(
        ocr_worker,
        "_read_image",
        lambda path: (b"image", f"hash-{path.stem}", Image.new("RGB", (10, 10), "white")),
    )
    _configure_session_policy(monkeypatch, max_pages=2)
    tasks = [{"book_name": "book", "page_no": page_no, "image_path": f"{page_no:03}.png"} for page_no in range(1, 6)]

    ocr_worker._run_surya(tasks)

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    pages = [event["page"] for event in events if event["event"] == "page"]
    starts = [
        event["progress"]
        for event in events
        if event["event"] == "progress" and event["progress"]["stage"] == "server_started"
    ]
    stops = [
        event["progress"]
        for event in events
        if event["event"] == "progress" and event["progress"]["stage"] == "server_stopping"
    ]

    assert [page["page_no"] for page in pages] == [1, 2, 3, 4, 5]
    assert [page["server_generation"] for page in pages] == [1, 1, 2, 2, 3]
    assert len(servers) == 3
    assert [event["server_generation"] for event in starts] == [1, 2, 3]
    assert [event["detail"] for event in stops] == ["page_limit", "page_limit", "completed"]


def test_worker_keeps_external_server_and_resets_policy_without_duplicate_results(
    monkeypatch,
    capsys,
) -> None:
    servers: list[object] = []

    class FakeServer:
        owns_process = False

        def __init__(self, *_args, **_kwargs) -> None:
            servers.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    class FakeClient:
        min_ink_coverage = 0.85

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def recognize_with_quality(self, _image, *, max_attempts):
            assert max_attempts == 1
            return _passed_result()

    monkeypatch.setattr(ocr_worker, "SuryaServer", FakeServer)
    monkeypatch.setattr(ocr_worker, "SuryaClient", FakeClient)
    monkeypatch.setattr(
        ocr_worker,
        "_read_image",
        lambda path: (b"image", f"hash-{path.stem}", Image.new("RGB", (10, 10), "white")),
    )
    _configure_session_policy(monkeypatch, max_pages=1)
    tasks = [{"book_name": "book", "page_no": page_no, "image_path": f"{page_no:03}.png"} for page_no in range(1, 4)]

    ocr_worker._run_surya(tasks)

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    pages = [event["page"] for event in events if event["event"] == "page"]
    skipped = [
        event["progress"]
        for event in events
        if event["event"] == "progress" and event["progress"]["stage"] == "server_restart_skipped"
    ]
    stops = [
        event["progress"]
        for event in events
        if event["event"] == "progress" and event["progress"]["stage"] == "server_stopping"
    ]

    assert [page["page_no"] for page in pages] == [1, 2, 3]
    assert [page["server_generation"] for page in pages] == [1, 1, 1]
    assert len(servers) == 1
    assert [event["detail"] for event in skipped] == [
        "page_limit:external_server",
        "page_limit:external_server",
    ]
    assert [event["detail"] for event in stops] == ["completed"]


def test_worker_emits_failed_page_and_continues_with_next_task(monkeypatch, capsys) -> None:
    class FakeServer:
        owns_process = False

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    class FakeClient:
        min_ink_coverage = 0.85

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def recognize_with_quality(self, _image, *, max_attempts):
            assert max_attempts == 1
            if getattr(self, "called", False):
                return _passed_result()
            self.called = True
            raise RuntimeError("page failed")

    monkeypatch.setattr(ocr_worker, "SuryaServer", FakeServer)
    monkeypatch.setattr(ocr_worker, "SuryaClient", FakeClient)
    monkeypatch.setattr(
        ocr_worker,
        "_read_image",
        lambda path: (b"image", f"hash-{path.stem}", Image.new("RGB", (10, 10), "white")),
    )
    _configure_session_policy(monkeypatch, max_pages=10)
    tasks = [
        {"book_name": "book", "page_no": 1, "image_path": "001.png"},
        {"book_name": "book", "page_no": 2, "image_path": "002.png"},
    ]

    ocr_worker._run_surya(tasks)

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    pages = [event["page"] for event in events if event["event"] == "page"]
    completed = [
        event["progress"]
        for event in events
        if event["event"] == "progress" and event["progress"]["stage"] == "page_completed"
    ]

    assert [page["page_no"] for page in pages] == [1, 2]
    assert pages[0]["state"] == "failed"
    assert pages[0]["image_sha256"] == "hash-001"
    assert pages[0]["quality_flags"] == ["worker_error"]
    assert pages[0]["error_message"] == "page failed"
    assert pages[1]["state"] == "passed"
    assert [event["detail"] for event in completed] == ["worker_error", "passed"]


def test_worker_standalone_cli_emits_fatal_event_for_empty_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text('{"tasks": []}', encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(Path(ocr_worker.__file__)), "--manifest", str(manifest_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout) == {"event": "fatal", "error": "OCR task list is empty"}
