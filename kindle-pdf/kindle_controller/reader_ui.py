from __future__ import annotations

import time
from _ctypes import COMError
from typing import Protocol

import pyautogui

from .models import ControllerConfig, KindleControllerError
from .reader_policy import PageLayoutPolicy


class ReaderControlHost(Protocol):
    config: ControllerConfig

    def _control_by_id(self, automation_id: str, **kwargs: object) -> object | None: ...

    def _edit_by_id(self, automation_id: str, **kwargs: object) -> object | None: ...

    def _button_by_id(self, automation_id: str, **kwargs: object) -> object | None: ...

    def _click_control(self, control: object) -> None: ...

    def _click_relative_to_control(
        self,
        control: object,
        *,
        x_offset: int,
        y_offset: int,
    ) -> bool: ...

    @staticmethod
    def _toggle_is_on(control: object) -> bool: ...


class ReaderUIAdapter:
    """Reader workflow から UIA/キーボード操作の詳細を隔離する。"""

    _PAGE_SETTINGS_REVEAL_ATTEMPTS = 2
    _PAGE_SETTINGS_POLL_SECONDS = 0.25

    def __init__(self, host: ReaderControlHost) -> None:
        self._host = host
        self._location_dialog_open = False

    def apply_page_layout(self, policy: PageLayoutPolicy) -> None:
        reading_area = self._host._control_by_id("ReadingArea", timeout=2.0)
        if reading_area is None:
            raise KindleControllerError(
                "positioning_failed",
                "Kindleの読書領域を取得できませんでした",
            )
        page_settings = self._open_page_settings(reading_area)
        try:
            self._select_and_verify_layout(policy)
        finally:
            self._close_page_settings(reading_area, page_settings)

    def _open_page_settings(self, reading_area: object) -> object:
        page_settings = self._host._control_by_id("aaMenuButton", timeout=0.5)
        for attempt in range(self._PAGE_SETTINGS_REVEAL_ATTEMPTS):
            if page_settings is not None:
                break
            visible_reading_area = self._host._control_by_id(
                "ReadingArea",
                timeout=1.0,
            )
            self._host._click_control(visible_reading_area or reading_area)
            page_settings = self._wait_for_page_settings_control()
            if (
                page_settings is None
                and attempt + 1 < self._PAGE_SETTINGS_REVEAL_ATTEMPTS
            ):
                pyautogui.press("esc")
                time.sleep(self._PAGE_SETTINGS_POLL_SECONDS)
        if page_settings is None:
            raise KindleControllerError(
                "positioning_failed",
                "Kindleのページ設定を開けませんでした",
            )
        self._host._click_control(page_settings)
        time.sleep(0.5)
        return page_settings

    def _wait_for_page_settings_control(self) -> object | None:
        deadline = time.monotonic() + self._host.config.control_timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            page_settings = self._host._control_by_id(
                "aaMenuButton",
                timeout=max(0.01, min(0.5, remaining)),
            )
            if page_settings is not None:
                return page_settings
            if remaining <= 0:
                return None
            time.sleep(min(self._PAGE_SETTINGS_POLL_SECONDS, remaining))

    def _select_and_verify_layout(self, policy: PageLayoutPolicy) -> None:
        option = self._host._control_by_id(policy.option_id, timeout=2.0)
        if option is None:
            if self._compatible_without_layout_option(policy):
                return
            raise KindleControllerError(
                "positioning_failed",
                "Kindleのページレイアウトを取得できませんでした",
            )
        if not self._host._toggle_is_on(option):
            self._host._click_control(option)
        self._wait_for_selected_layout(policy.option_id)

    def _compatible_without_layout_option(self, policy: PageLayoutPolicy) -> bool:
        fallback_id = policy.compatible_without_option_id
        return (
            fallback_id is not None
            and self._host._control_by_id(
                fallback_id,
                timeout=1.0,
            )
            is not None
        )

    def _wait_for_selected_layout(self, option_id: str) -> None:
        deadline = time.monotonic() + self._host.config.control_timeout_seconds
        while time.monotonic() < deadline:
            option = self._host._control_by_id(option_id, timeout=0.5)
            if option is not None and self._host._toggle_is_on(option):
                return
            time.sleep(0.25)
        raise KindleControllerError(
            "positioning_failed",
            "Kindleのページレイアウトを確認できませんでした",
        )

    def _close_page_settings(
        self,
        reading_area: object,
        _page_settings: object,
    ) -> None:
        close_button = self._host._control_by_id(
            "CloseSideMenuHeaderButton",
            timeout=1.0,
        )
        if close_button is not None:
            self._host._click_control(close_button)
        else:
            pyautogui.press("esc")
        time.sleep(0.25)
        if self._host._control_by_id("aaMenuButton", timeout=0.5) is not None:
            visible_reading_area = self._host._control_by_id(
                "ReadingArea",
                timeout=1.0,
            )
            if visible_reading_area is not None:
                self._host._click_control(visible_reading_area)
                time.sleep(0.25)

    def open_location_dialog(self) -> bool:
        reading_area = self._host._control_by_id("ReadingArea", timeout=1.0)
        if reading_area is None:
            return False
        more_menu = self._host._button_by_id("moreMenuButton", timeout=0.5)
        if more_menu is None:
            self._host._click_control(reading_area)
            time.sleep(0.25)
            more_menu = self._host._button_by_id("moreMenuButton", timeout=1.0)
        if more_menu is None:
            return False

        self._host._click_control(more_menu)
        self._location_dialog_open = True
        time.sleep(0.25)
        if not self._host._click_relative_to_control(
            more_menu,
            x_offset=-30,
            y_offset=45,
        ):
            return False
        time.sleep(0.25)
        return self._host._edit_by_id("go-to-page-input", timeout=1.0) is not None

    def set_location_value(self, value: str) -> bool:
        location_input = self._host._edit_by_id("go-to-page-input", timeout=1.0)
        if location_input is None:
            return False
        try:
            value_pattern = location_input.GetValuePattern()  # type: ignore[attr-defined]
            value_pattern.SetValue(value)
            time.sleep(0.1)
            raw_value = value_pattern.Value
        except (AttributeError, COMError, TypeError, ValueError):
            return False
        return raw_value is not None and str(raw_value) == value

    def confirm_location(self) -> bool:
        confirm = self._host._button_by_id("modal-confirm", timeout=1.0)
        if confirm is None:
            return False
        self._host._click_control(confirm)
        for _attempt in range(20):
            if self._host._edit_by_id("go-to-page-input", timeout=0.25) is None:
                self._location_dialog_open = False
                return True
            time.sleep(0.1)
        return False

    def dismiss_location_dialog(self) -> None:
        if not self._location_dialog_open:
            return
        pyautogui.press("esc")
        time.sleep(0.1)
        self._location_dialog_open = False

    def show_chrome(self) -> bool:
        reading_area = self._host._control_by_id("ReadingArea", timeout=1.0)
        if reading_area is None:
            return False
        self._host._click_control(reading_area)
        time.sleep(0.25)
        return True

    @staticmethod
    def press_key(key: str) -> None:
        pyautogui.press(key)
