from __future__ import annotations

import json

from PIL import Image

from services.novel_db import ocr_worker
from services.novel_db.surya_ocr import SuryaBlock, SuryaPageResult


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
            return SuryaPageResult(
                full_text="本文",
                raw_output='<div data-label="Text" data-bbox="0 0 1000 1000">本文</div>',
                blocks=[SuryaBlock("Text", (0, 0, 1000, 1000), "本文")],
                state="passed",
                quality_flags=[],
                ink_coverage=1.0,
                attempt_count=1,
            )

    monkeypatch.setattr(ocr_worker, "SuryaServer", FakeServer)
    monkeypatch.setattr(ocr_worker, "SuryaClient", FakeClient)
    monkeypatch.setattr(
        ocr_worker,
        "_read_image",
        lambda path: (b"image", f"hash-{path.stem}", Image.new("RGB", (10, 10), "white")),
    )
    monkeypatch.setenv("SURYA_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("OCR_SERVER_MAX_PAGES", "2")
    monkeypatch.setenv("OCR_SERVER_CONSECUTIVE_FAILURES", "2")
    monkeypatch.setenv("OCR_SERVER_FAILURE_WINDOW", "4")
    monkeypatch.setenv("OCR_SERVER_FAILURE_RATE", "0.5")
    monkeypatch.setenv("OCR_CROSSCHECK_ALL_PAGES", "false")
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
