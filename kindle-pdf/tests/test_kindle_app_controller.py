from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

import kindle_app_controller as controller_module
from kindle_app_controller import (
    BookCandidate,
    BookIdentity,
    ControllerConfig,
    KindleAppController,
    KindleControllerError,
    candidate_matches_identity,
    select_verified_candidate,
    visual_frames_differ,
)


def _identity(**overrides) -> BookIdentity:
    values = {
        "asin": "B012345678",
        "title": "十三歳の誕生日、皇后になりました。 1",
        "title_normalized": "十三歳の誕生日、皇后になりました。1",
        "authors": ("石田リンネ",),
        "series_name": "十三歳の誕生日、皇后になりました。",
        "volume_number": 1.0,
        "volume_label": "1",
    }
    values.update(overrides)
    return BookIdentity(**values)


def test_asin_exact_match_has_priority() -> None:
    candidate = BookCandidate(
        asin="B012345678",
        title="アクセシブル名が正式タイトルと異なる",
    )

    assert candidate_matches_identity(_identity(), candidate)


def test_asin_mismatch_is_rejected_even_when_title_matches() -> None:
    candidate = BookCandidate(
        asin="B999999999",
        title="十三歳の誕生日、皇后になりました。1",
        authors=("石田リンネ",),
    )

    assert not candidate_matches_identity(_identity(), candidate)


def test_normalized_title_and_author_match_without_asin() -> None:
    candidate = BookCandidate(
        asin=None,
        title="十三歳の誕生日、皇后になりました。１",
        authors=("石田リンネ",),
    )

    assert candidate_matches_identity(_identity(), candidate)


def test_series_and_volume_match_without_author() -> None:
    candidate = BookCandidate(
        asin=None,
        title="十三歳の誕生日、皇后になりました。1",
        series_name="十三歳の誕生日、皇后になりました。",
        volume_number=1.0,
    )

    assert candidate_matches_identity(_identity(), candidate)


def test_title_only_is_not_enough_without_asin() -> None:
    candidate = BookCandidate(
        asin=None,
        title="十三歳の誕生日、皇后になりました。1",
    )

    assert not candidate_matches_identity(_identity(), candidate)


def test_candidate_not_found_and_ambiguous_have_distinct_codes() -> None:
    with pytest.raises(KindleControllerError) as missing:
        select_verified_candidate(_identity(), [])
    assert missing.value.error_code == "book_not_found"

    candidates = [
        BookCandidate(asin="B012345678", title="候補1"),
        BookCandidate(asin="B012345678", title="候補2"),
    ]
    with pytest.raises(KindleControllerError) as ambiguous:
        select_verified_candidate(_identity(), candidates)
    assert ambiguous.value.error_code == "book_match_ambiguous"


def test_visual_frames_differ_detects_page_change() -> None:
    white = Image.new("RGB", (200, 300), "white")
    same_white = Image.new("RGB", (200, 300), "white")
    black = Image.new("RGB", (200, 300), "black")

    assert not visual_frames_differ(white, same_white)
    assert visual_frames_differ(white, black)


def test_content_snapshot_requires_official_nonempty_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_app_data = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    content = (
        local_app_data
        / "Packages"
        / "AMZNKindle.AmazonKindleReadingApp_m1sc522ngdk36"
        / "LocalState"
        / "Classic"
        / "Content"
        / "B012345678_EBOK"
    )
    content.mkdir(parents=True)
    (content / "book.azw").write_bytes(b"azw")
    controller = KindleAppController()

    assert controller._content_snapshot("B012345678") is None

    (content / "book.voucher").write_bytes(b"voucher")
    snapshot = controller._content_snapshot("B012345678")

    assert snapshot is not None
    assert snapshot[:2] == (2, 10)


class _Button:
    def __init__(self, name: str) -> None:
        self.Name = name
        self.clicked = False

    def Click(self, **_kwargs) -> None:
        self.clicked = True


class _DownloadController(KindleAppController):
    def __init__(
        self,
        controls: list[_Button | None],
        snapshots: list[tuple[int, int, int] | None],
        config: ControllerConfig,
    ) -> None:
        super().__init__(config)
        self.controls = controls
        self.snapshots = snapshots

    def _control_by_id(self, *_args, **_kwargs):
        if len(self.controls) > 1:
            return self.controls.pop(0)
        return self.controls[0]

    def _content_snapshot(self, _asin: str):
        if len(self.snapshots) > 1:
            return self.snapshots.pop(0)
        return self.snapshots[0]

    def _ensure_process_running(self) -> None:
        return None


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class _PositionController(KindleAppController):
    def __init__(self, frames: list[Image.Image], config: ControllerConfig) -> None:
        super().__init__(config)
        self.frames = frames

    def wait_for_reader_stable(self) -> None:
        return None

    def _reading_area_image(self, *, timeout: float = 1.0) -> Image.Image | None:
        del timeout
        if len(self.frames) > 1:
            return self.frames.pop(0)
        return self.frames[0]

    def _ensure_process_running(self) -> None:
        return None


def test_go_to_start_stops_after_three_unchanged_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page_two = Image.new("RGB", (100, 100), "black")
    page_one = Image.new("RGB", (100, 100), "white")
    controller = _PositionController(
        [page_two, page_one, page_one, page_one, page_one],
        ControllerConfig(
            positioning_timeout_seconds=10,
            page_stable_seconds=1,
            start_boundary_checks=3,
        ),
    )
    clock = _Clock()
    presses: list[str] = []
    polls: list[bool] = []
    monkeypatch.setattr(controller_module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(controller_module.time, "sleep", clock.sleep)
    monkeypatch.setattr(
        controller_module.pyautogui,
        "press",
        lambda key: presses.append(key),
    )

    controller.go_to_start(on_poll=lambda: polls.append(True))

    assert presses == ["pageup"] * 4
    assert len(polls) == 4


def test_download_waits_for_button_disappearance_and_stable_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start = _Button("ダウンロード")
    downloading = _Button("ダウンロードをキャンセルする")
    controller = _DownloadController(
        [start, downloading, None, None],
        [(10, 1000, 1), (10, 1000, 1)],
        ControllerConfig(
            download_timeout_seconds=10,
            download_poll_seconds=1,
            download_stable_checks=2,
        ),
    )
    clock = _Clock()
    monkeypatch.setattr(controller_module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(controller_module.time, "sleep", clock.sleep)

    controller.wait_for_download(BookCandidate(asin="B012345678", title="target"))

    assert start.clicked


def test_download_timeout_has_distinct_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    downloading = _Button("ダウンロードをキャンセルする")
    controller = _DownloadController(
        [downloading],
        [None],
        ControllerConfig(download_timeout_seconds=3, download_poll_seconds=1),
    )
    clock = _Clock()
    monkeypatch.setattr(controller_module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(controller_module.time, "sleep", clock.sleep)

    with pytest.raises(KindleControllerError) as exc:
        controller.wait_for_download(BookCandidate(asin="B012345678", title="target"))

    assert exc.value.error_code == "download_timeout"


def test_missing_download_state_fails_without_opening_book(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _DownloadController(
        [None],
        [None],
        ControllerConfig(download_timeout_seconds=3, download_poll_seconds=1),
    )
    clock = _Clock()
    monkeypatch.setattr(controller_module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(controller_module.time, "sleep", clock.sleep)

    with pytest.raises(KindleControllerError) as exc:
        controller.wait_for_download(BookCandidate(asin="B012345678", title="target"))

    assert exc.value.error_code == "download_failed"
