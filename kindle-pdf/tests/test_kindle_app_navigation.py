from __future__ import annotations

from types import SimpleNamespace

import pytest

import kindle_app_controller as controller_module
from kindle_app_controller import (
    BookCandidate,
    ControllerConfig,
    KindleAppController,
    KindleControllerError,
)

from tests.kindle_app_test_doubles import (
    _Button,
    _Clock,
    _DownloadController,
    _LayoutControl,
    _LayoutController,
    _LocationControl,
    _LocationController,
    _PositionController,
)


def test_popup_control_must_be_within_kindle_window() -> None:
    controller = KindleAppController()
    controller.window = SimpleNamespace(
        BoundingRectangle=SimpleNamespace(left=100, top=100, right=900, bottom=700)
    )
    inside = SimpleNamespace(
        BoundingRectangle=SimpleNamespace(left=700, top=200, right=800, bottom=300)
    )
    outside = SimpleNamespace(
        BoundingRectangle=SimpleNamespace(left=950, top=200, right=1050, bottom=300)
    )

    assert controller._control_is_within_window(inside)
    assert not controller._control_is_within_window(outside)


def test_control_keyboard_activation_focuses_before_enter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control = _LocationControl("backButton")
    presses: list[str] = []
    monkeypatch.setattr(
        controller_module.pyautogui,
        "press",
        lambda key: presses.append(key),
    )

    KindleAppController._activate_control_with_keyboard(control)

    assert control.focused
    assert presses == ["enter"]


def test_go_to_start_fails_without_sequential_page_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _PositionController(ControllerConfig())
    presses: list[str] = []
    polls: list[bool] = []
    monkeypatch.setattr(
        controller_module.pyautogui,
        "press",
        lambda key: presses.append(key),
    )

    with pytest.raises(KindleControllerError) as exc:
        controller.go_to_start(
            source="novel",
            direction="left",
            on_poll=lambda: polls.append(True),
        )

    assert exc.value.error_code == "positioning_failed"
    assert presses == []
    assert polls == []


@pytest.mark.parametrize(
    ("source", "footer_name", "expected"),
    [
        ("novel", "Location 1 of 3304  • 0%", True),
        ("novel", "Location 2 of 3304  • 0%", True),
        ("novel", "Location 4 of 4006  • 0%", True),
        ("novel", "Location 5 of 4006  • 0%", False),
        ("novel", "Location 4 of 4006  • 1%", False),
        ("novel", "ページ1/233  • 0%", True),
        ("novel", "ページ2/233  • 0%", False),
        ("comic", "Location 1 of 169  • 0%", True),
        ("comic", "Location 2 of 169  • 0%", True),
        ("comic", "Location 2 of 169  • 1%", False),
        ("comic", "ページ1/85  • 0%", False),
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
    ("source", "footer_name", "expected_presses"),
    [
        ("novel", "Location 1 of 3304  • 0%", []),
        ("novel", "Location 4 of 4006  • 0%", []),
        ("novel", "ページ1/233  • 0%", ["right"]),
        ("comic", "Location 2 of 169  • 0%", []),
    ],
)
def test_go_to_start_uses_direct_location_and_at_most_one_cover_step(
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    footer_name: str,
    expected_presses: list[str],
) -> None:
    controller = _LocationController(footer_name)
    presses: list[str] = []
    polls: list[bool] = []
    edit = controller.controls["go-to-page-input"]
    monkeypatch.setattr(controller_module.time, "sleep", lambda _seconds: None)

    def _press(key: str) -> None:
        presses.append(key)
        if key == "right" and source == "novel" and footer_name.startswith("ページ1/"):
            controller.controls["FooterLabelText"].Name = "Location 1 of 3304  • 0%"

    monkeypatch.setattr(controller_module.pyautogui, "press", _press)

    assert controller._try_go_to_location_start(
        source=source,
        direction="left",
        on_poll=lambda: polls.append(True),
    )

    expected_clicks = [
        "moreMenuButton",
        "moreMenuButton:first-item",
        "modal-confirm",
    ]
    if expected_presses:
        expected_clicks.append("ReadingArea")
    assert controller.clicked == expected_clicks
    assert controller.keyboard_activated == []
    assert not edit.focused
    assert edit.value_pattern.Value == "1"
    assert presses == expected_presses
    assert controller.stable_waits == 1 + len(expected_presses)
    assert polls


def test_go_to_start_accepts_current_cover_without_opening_dialog() -> None:
    controller = _LocationController("Location 4 of 4006  • 0%")

    controller.go_to_start(source="novel", direction="right")

    assert controller.clicked == []
    assert controller.keyboard_activated == []
    assert controller.stable_waits == 0


def test_go_to_start_waits_for_delayed_cover_footer_without_extra_page_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _LocationController("ページ1/233  • 0%")
    original_control_by_id = controller._control_by_id
    footer_lookups = 0
    presses: list[str] = []
    monkeypatch.setattr(controller_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(controller_module.pyautogui, "hotkey", lambda *_keys: None)

    def _write(value: str, interval: float) -> None:
        del interval
        controller.controls["go-to-page-input"].value_pattern.Value = value

    def _press(key: str) -> None:
        presses.append(key)

    def _control_by_id(automation_id: str, **kwargs):
        nonlocal footer_lookups
        if automation_id == "FooterLabelText":
            footer_lookups += 1
            if footer_lookups >= 7:
                controller.controls["FooterLabelText"].Name = "Location 1 of 3304  • 0%"
        return original_control_by_id(automation_id, **kwargs)

    monkeypatch.setattr(controller_module.pyautogui, "write", _write)
    monkeypatch.setattr(controller_module.pyautogui, "press", _press)
    monkeypatch.setattr(controller, "_control_by_id", _control_by_id)

    controller.go_to_start(source="novel", direction="left")

    assert presses == ["right"]
    assert footer_lookups == 7


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
    edit = controller.controls["go-to-page-input"]
    edit.value_pattern.SetValue = lambda _value: None
    monkeypatch.setattr(controller_module.pyautogui, "press", lambda _key: None)
    monkeypatch.setattr(
        controller_module.pyautogui,
        "press",
        lambda key: presses.append(key),
    )

    assert not controller._try_go_to_location_start("novel")
    assert "esc" in presses
    assert "modal-confirm" not in controller.clicked


def test_location_start_rejects_missing_value_readback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _LocationController("Location 2 of 169  • 0%")
    edit = controller.controls["go-to-page-input"]
    edit.value_pattern.SetValue = lambda _value: setattr(
        edit.value_pattern,
        "Value",
        None,
    )
    monkeypatch.setattr(controller_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(controller_module.pyautogui, "hotkey", lambda *_keys: None)
    monkeypatch.setattr(
        controller_module.pyautogui,
        "write",
        lambda _value, interval: None,
    )

    assert not controller._try_go_to_location_start("comic")
    assert "modal-confirm" not in controller.clicked


def test_location_start_rejects_confirmed_dialog_that_remains_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _LocationController("Location 1 of 3304  • 0%")
    edit = controller.controls["go-to-page-input"]
    presses: list[str] = []
    monkeypatch.setattr(controller_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(controller_module.pyautogui, "hotkey", lambda *_keys: None)

    def _write(value: str, interval: float) -> None:
        del interval
        edit.value_pattern.Value = value

    monkeypatch.setattr(controller_module.pyautogui, "write", _write)
    monkeypatch.setattr(controller_module.pyautogui, "press", lambda _key: None)
    monkeypatch.setattr(
        controller_module.pyautogui,
        "press",
        lambda key: presses.append(key),
    )
    original_click_control = controller._click_control

    def _click_control(control: _LocationControl) -> None:
        if control.AutomationId == "modal-confirm":
            controller.clicked.append(control.AutomationId)
            return
        original_click_control(control)

    monkeypatch.setattr(controller, "_click_control", _click_control)

    assert not controller._try_go_to_location_start("novel")
    assert "esc" in presses
    assert controller.stable_waits == 0


def test_location_start_waits_for_stale_dialog_control_to_disappear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _LocationController("Location 4 of 4006  • 0%")
    edit = controller.controls["go-to-page-input"]
    original_edit_by_id = controller._edit_by_id
    stale_lookups = 0
    monkeypatch.setattr(controller_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(controller_module.pyautogui, "hotkey", lambda *_keys: None)

    def _write(value: str, interval: float) -> None:
        del interval
        edit.value_pattern.Value = value

    def _edit_by_id(automation_id: str, **kwargs):
        nonlocal stale_lookups
        if (
            automation_id == "go-to-page-input"
            and "modal-confirm" in controller.clicked
        ):
            stale_lookups += 1
            if stale_lookups <= 12:
                return edit
        return original_edit_by_id(automation_id, **kwargs)

    monkeypatch.setattr(controller_module.pyautogui, "write", _write)
    monkeypatch.setattr(controller, "_edit_by_id", _edit_by_id)

    assert controller._try_go_to_location_start("novel", direction="right")
    assert stale_lookups == 13
    assert controller.stable_waits == 1


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
