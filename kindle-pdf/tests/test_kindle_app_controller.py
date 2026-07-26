from __future__ import annotations

from _ctypes import COMError
from pathlib import Path
from types import SimpleNamespace

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


def test_control_lookup_treats_transient_com_error_as_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _TransientControl:
        def Exists(self, *_args) -> bool:
            raise COMError(
                -2147220991,
                "event subscriber unavailable",
                (None, None, None, 0, None),
            )

    controller = KindleAppController()
    controller.window = object()
    monkeypatch.setattr(
        controller_module.auto,
        "Control",
        lambda **_kwargs: _TransientControl(),
    )

    assert controller._control_by_id("backButton", timeout=0.1) is None


def test_search_value_focuses_control_and_verifies_keyboard_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pattern = SimpleNamespace(Value="")
    focused: list[bool] = []
    edit = SimpleNamespace(
        SetFocus=lambda: focused.append(True),
        GetValuePattern=lambda: pattern,
    )
    controller = KindleAppController()
    monkeypatch.setattr(controller, "_search_edit", lambda **_kwargs: edit)
    hotkeys: list[tuple[str, ...]] = []
    writes: list[tuple[str, float]] = []
    monkeypatch.setattr(
        controller_module.pyautogui,
        "hotkey",
        lambda *keys: hotkeys.append(keys),
    )

    def _write(value: str, interval: float) -> None:
        writes.append((value, interval))
        pattern.Value = value

    monkeypatch.setattr(controller_module.pyautogui, "write", _write)
    monkeypatch.setattr(controller_module.time, "sleep", lambda _seconds: None)

    controller._set_search_value("B012345678")

    assert focused == [True]
    assert hotkeys == [("ctrl", "a")]
    assert writes == [("B012345678", 0.02)]


def test_control_center_rejects_invalid_bounds() -> None:
    control = SimpleNamespace(
        BoundingRectangle=SimpleNamespace(left=20, top=20, right=10, bottom=40)
    )

    with pytest.raises(KindleControllerError) as exc:
        KindleAppController._control_center(control)

    assert exc.value.error_code == "kindle_ui_unavailable"


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


class _ToggleElement:
    def __init__(self, on: bool) -> None:
        self.on = on

    def GetCurrentPropertyValue(self, _property_id: int) -> int:
        return int(self.on)


class _LayoutControl:
    def __init__(self, automation_id: str, *, on: bool = False) -> None:
        self.AutomationId = automation_id
        self.Element = _ToggleElement(on)
        self.BoundingRectangle = SimpleNamespace(
            left=10,
            top=20,
            right=110,
            bottom=60,
        )


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

    def _click_control(self, control: _Button) -> None:
        control.clicked = True


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

    def _try_go_to_location_start(
        self,
        source: str,
        *,
        on_poll=None,
    ) -> bool:
        del source, on_poll
        return False


class _LayoutController(KindleAppController):
    def __init__(self) -> None:
        super().__init__(ControllerConfig(control_timeout_seconds=0.2))
        self.controls = {
            "ReadingArea": _LayoutControl("ReadingArea"),
            "aaMenuButton": _LayoutControl("aaMenuButton"),
            "aaOption-Split": _LayoutControl("aaOption-Split"),
            "aaOption-Single": _LayoutControl("aaOption-Single", on=True),
            "CloseSideMenuHeaderButton": _LayoutControl("CloseSideMenuHeaderButton"),
        }
        self.clicked: list[str] = []

    def _control_by_id(self, automation_id: str, **_kwargs):
        return self.controls.get(automation_id)

    def _click_control(self, control: _LayoutControl) -> None:
        self.clicked.append(control.AutomationId)
        if control.AutomationId == "aaOption-Split":
            self.controls["aaOption-Split"].Element.on = True
            self.controls["aaOption-Single"].Element.on = False
        elif control.AutomationId == "aaOption-Single":
            self.controls["aaOption-Split"].Element.on = False
            self.controls["aaOption-Single"].Element.on = True


class _LocationControl(_LayoutControl):
    def __init__(
        self,
        automation_id: str,
        *,
        name: str = "",
        value: str = "",
    ) -> None:
        super().__init__(automation_id)
        self.Name = name
        self.value_pattern = SimpleNamespace(Value=value)
        self.focused = False

    def SetFocus(self) -> None:
        self.focused = True

    def GetValuePattern(self):
        return self.value_pattern


class _LocationController(KindleAppController):
    def __init__(self, footer_name: str) -> None:
        super().__init__(ControllerConfig(control_timeout_seconds=0.2))
        self.controls = {
            "ReadingArea": _LocationControl("ReadingArea"),
            "moreMenuButton": _LocationControl(
                "moreMenuButton",
                name="もっと",
            ),
            "go-to-page-input": _LocationControl(
                "go-to-page-input",
                name="ロケーション番号入力",
            ),
            "FooterLabelText": _LocationControl(
                "FooterLabelText",
                name=footer_name,
            ),
        }
        self.named_controls = {
            ("位置に移動", "btn-popover-menu-item"): _LocationControl(
                "btn-popover-menu-item",
                name="位置に移動",
            ),
            ("位置に移動", "modal-confirm"): _LocationControl(
                "modal-confirm",
                name="位置に移動",
            ),
        }
        self.clicked: list[str] = []
        self.stable_waits = 0

    def _control_by_id(self, automation_id: str, **_kwargs):
        return self.controls.get(automation_id)

    def _control_by_name(
        self,
        name: str,
        *,
        automation_id: str,
        **_kwargs,
    ):
        return self.named_controls.get((name, automation_id))

    def _click_control(self, control: _LocationControl) -> None:
        self.clicked.append(control.AutomationId)

    def _ensure_process_running(self) -> None:
        return None

    def wait_for_reader_stable(self) -> None:
        self.stable_waits += 1


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

    controller.go_to_start(
        source="novel",
        direction="left",
        on_poll=lambda: polls.append(True),
    )

    assert presses == ["right"] * 4
    assert len(polls) == 4


@pytest.mark.parametrize(
    ("source", "footer_name", "expected"),
    [
        ("novel", "Location 1 of 3304  • 0%", True),
        ("novel", "Location 2 of 3304  • 0%", False),
        ("comic", "Location 1 of 169  • 0%", True),
        ("comic", "Location 2 of 169  • 0%", True),
        ("comic", "Location 2 of 169  • 1%", False),
        ("comic", "", False),
    ],
)
def test_footer_start_detection_is_source_specific(
    source: str,
    footer_name: str,
    expected: bool,
) -> None:
    assert controller_module._footer_indicates_start(source, footer_name) is expected


@pytest.mark.parametrize(
    ("source", "footer_name"),
    [
        ("novel", "Location 1 of 3304  • 0%"),
        ("comic", "Location 2 of 169  • 0%"),
    ],
)
def test_go_to_start_uses_location_dialog_before_page_fallback(
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    footer_name: str,
) -> None:
    controller = _LocationController(footer_name)
    hotkeys: list[tuple[str, ...]] = []
    writes: list[tuple[str, float]] = []
    presses: list[str] = []
    polls: list[bool] = []
    edit = controller.controls["go-to-page-input"]
    monkeypatch.setattr(controller_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        controller_module.pyautogui,
        "hotkey",
        lambda *keys: hotkeys.append(keys),
    )

    def _write(value: str, interval: float) -> None:
        writes.append((value, interval))
        edit.value_pattern.Value = value

    monkeypatch.setattr(controller_module.pyautogui, "write", _write)
    monkeypatch.setattr(
        controller_module.pyautogui,
        "press",
        lambda key: presses.append(key),
    )

    controller.go_to_start(
        source=source,
        direction="left",
        on_poll=lambda: polls.append(True),
    )

    assert controller.clicked == [
        "moreMenuButton",
        "btn-popover-menu-item",
        "modal-confirm",
    ]
    assert edit.focused
    assert hotkeys == [("ctrl", "a")]
    assert writes == [("1", 0.02)]
    assert presses == []
    assert controller.stable_waits == 1
    assert polls


def test_location_start_rejects_unverified_keyboard_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _LocationController("Location 1 of 3304  • 0%")
    presses: list[str] = []
    monkeypatch.setattr(controller_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(controller_module.pyautogui, "hotkey", lambda *_keys: None)
    monkeypatch.setattr(
        controller_module.pyautogui,
        "write",
        lambda _value, interval: None,
    )
    monkeypatch.setattr(
        controller_module.pyautogui,
        "press",
        lambda key: presses.append(key),
    )

    assert not controller._try_go_to_location_start("novel")
    assert "esc" in presses
    assert "modal-confirm" not in controller.clicked


def test_location_start_accepts_missing_value_readback_when_footer_verifies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _LocationController("Location 2 of 169  • 0%")
    edit = controller.controls["go-to-page-input"]
    edit.value_pattern.Value = None
    monkeypatch.setattr(controller_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(controller_module.pyautogui, "hotkey", lambda *_keys: None)
    monkeypatch.setattr(
        controller_module.pyautogui,
        "write",
        lambda _value, interval: None,
    )

    assert controller._try_go_to_location_start("comic")
    assert "modal-confirm" in controller.clicked


def test_page_layout_selects_spread_and_verifies_toggle_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _LayoutController()
    monkeypatch.setattr(controller_module.time, "sleep", lambda _seconds: None)

    controller.set_page_layout("comic")

    assert controller.controls["aaOption-Split"].Element.on
    assert "aaOption-Split" in controller.clicked
    assert "CloseSideMenuHeaderButton" in controller.clicked


def test_page_layout_accepts_reflowable_novel_without_page_count_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _LayoutController()
    controller.controls.pop("aaOption-Single")
    controller.controls["フォント-item"] = _LayoutControl("フォント-item")
    monkeypatch.setattr(controller_module.time, "sleep", lambda _seconds: None)

    controller.set_page_layout("novel")

    assert "aaOption-Split" not in controller.clicked
    assert "CloseSideMenuHeaderButton" in controller.clicked


def test_reading_area_bounds_returns_verified_rectangle() -> None:
    controller = _LayoutController()
    controller.controls["ReadingArea"].BoundingRectangle = SimpleNamespace(
        left=0,
        top=48,
        right=3840,
        bottom=2112,
    )

    assert controller.reading_area_bounds() == (0, 48, 3840, 2112)


def test_capture_area_bounds_excludes_novel_header_and_footer() -> None:
    controller = _LayoutController()
    controller.controls["ReadingArea"].BoundingRectangle = SimpleNamespace(
        left=0,
        top=48,
        right=3840,
        bottom=2112,
    )
    controller.controls["TopChrome"] = _LayoutControl("TopChrome")
    controller.controls["TopChrome"].BoundingRectangle = SimpleNamespace(
        left=0,
        top=48,
        right=3840,
        bottom=100,
    )
    controller.controls["Footer"] = _LayoutControl("Footer")
    controller.controls["Footer"].BoundingRectangle = SimpleNamespace(
        left=0,
        top=2040,
        right=3840,
        bottom=2112,
    )

    assert controller.capture_area_bounds("novel") == (0, 100, 3840, 2040)
    assert controller.capture_area_bounds("comic") == (0, 48, 3840, 2112)


def test_capture_area_bounds_rejects_invalid_novel_controls() -> None:
    controller = _LayoutController()
    controller.controls["ReadingArea"].BoundingRectangle = SimpleNamespace(
        left=0,
        top=48,
        right=3840,
        bottom=2112,
    )
    controller.controls["TopChrome"] = _LayoutControl("TopChrome")
    controller.controls["TopChrome"].BoundingRectangle = SimpleNamespace(
        left=0,
        top=48,
        right=3840,
        bottom=2050,
    )
    controller.controls["Footer"] = _LayoutControl("Footer")
    controller.controls["Footer"].BoundingRectangle = SimpleNamespace(
        left=0,
        top=2040,
        right=3840,
        bottom=2112,
    )

    with pytest.raises(KindleControllerError) as exc:
        controller.capture_area_bounds("novel")

    assert exc.value.error_code == "kindle_ui_unavailable"


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
