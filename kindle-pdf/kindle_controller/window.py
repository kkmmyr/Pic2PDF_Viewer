import ctypes
import logging
import subprocess
import time
from _ctypes import COMError

import pyautogui
import uiautomation as auto

from .models import ControllerConfig, KindleControllerError

logger = logging.getLogger(__name__)


class WindowController:
    def __init__(self, config: ControllerConfig | None = None) -> None:
        self.config = config or ControllerConfig()
        self.window: auto.Control | None = None

    @staticmethod
    def _is_process_running() -> bool:
        result = subprocess.run(
            [
                "tasklist",
                "/FI",
                "IMAGENAME eq Kindle.exe",
                "/FO",
                "CSV",
                "/NH",
            ],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return '"kindle.exe"' in result.stdout.casefold()

    def _ensure_process_running(self) -> None:
        if not self._is_process_running():
            raise KindleControllerError(
                "kindle_app_exited",
                "処理中にKindleアプリが終了しました",
            )

    def attach_running_app(self) -> None:
        if not self._is_process_running():
            raise KindleControllerError(
                "kindle_not_running",
                "Kindleアプリが起動していません",
            )
        window = auto.WindowControl(searchDepth=1, Name=self.config.window_title)
        if not window.Exists(
            self.config.control_timeout_seconds,
            0.5,
        ):
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleウィンドウを取得できませんでした",
            )
        if window.ClassName != self.config.window_class_name:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "対応していないKindleウィンドウが見つかりました",
            )
        try:
            window_handle = int(window.NativeWindowHandle)
        except (AttributeError, COMError, TypeError, ValueError) as exc:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleウィンドウの識別情報を取得できませんでした",
            ) from exc
        user32 = ctypes.windll.user32
        if window_handle <= 0 or not user32.IsWindow(window_handle):
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleウィンドウの識別情報が不正です",
            )
        user32.ShowWindow(window_handle, 9)
        user32.SetForegroundWindow(window_handle)
        time.sleep(self.config.screen_transition_seconds)
        self.window = window

    def _require_window(self) -> auto.Control:
        if self.window is None:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleウィンドウへ接続していません",
            )
        return self.window

    def _control_by_id(
        self,
        automation_id: str,
        *,
        timeout: float | None = None,
        found_index: int = 1,
    ) -> auto.Control | None:
        control = auto.Control(
            searchFromControl=self._require_window(),
            searchDepth=self.config.control_search_depth,
            foundIndex=found_index,
            AutomationId=automation_id,
        )
        try:
            if control.Exists(
                self.config.control_timeout_seconds if timeout is None else timeout,
                0.5,
            ):
                return control
        except COMError:
            logger.debug(
                "Kindle UI Automation control lookup failed transiently: %s",
                automation_id,
                exc_info=True,
            )
        return None

    def _search_edit(self, timeout: float | None = None) -> auto.Control | None:
        edit = auto.EditControl(
            searchFromControl=self._require_window(),
            searchDepth=self.config.control_search_depth,
            Name="検索ライブラリ",
        )
        try:
            if edit.Exists(
                self.config.control_timeout_seconds if timeout is None else timeout,
                0.5,
            ):
                return edit
        except COMError:
            logger.debug(
                "Kindle UI Automation search field lookup failed transiently",
                exc_info=True,
            )
        return None

    def _control_by_name(
        self,
        name: str,
        *,
        automation_id: str,
        timeout: float | None = None,
    ) -> auto.Control | None:
        """NameとAutomationIdを併用して同名・同ID controlの誤選択を防ぐ。"""
        effective_timeout = (
            self.config.control_timeout_seconds if timeout is None else timeout
        )
        control = auto.Control(
            searchFromControl=self._require_window(),
            searchDepth=self.config.control_search_depth,
            Name=name,
            AutomationId=automation_id,
        )
        try:
            if control.Exists(effective_timeout, 0.5):
                return control
        except COMError:
            logger.debug(
                "Kindle UI Automation named control lookup failed transiently: %s",
                automation_id,
                exc_info=True,
            )

        # Microsoft Store版のpopoverはKindle本体とは別のUI Automation rootへ
        # 公開される場合がある。デスクトップ全体から限定探索し、座標が現在の
        # Kindleウィンドウ内にあるcontrolだけを受け入れる。
        popup_control = auto.Control(
            searchDepth=10,
            Name=name,
            AutomationId=automation_id,
        )
        try:
            if popup_control.Exists(effective_timeout, 0.5) and (
                self._control_is_within_window(popup_control)
            ):
                return popup_control
        except COMError:
            logger.debug(
                "Kindle popup control lookup failed transiently: %s",
                automation_id,
                exc_info=True,
            )
        return None

    def _control_is_within_window(self, control: object) -> bool:
        try:
            window_bounds = self._require_window().BoundingRectangle
            control_bounds = control.BoundingRectangle
            center_x = (int(control_bounds.left) + int(control_bounds.right)) // 2
            center_y = (int(control_bounds.top) + int(control_bounds.bottom)) // 2
            return int(window_bounds.left) <= center_x <= int(
                window_bounds.right
            ) and int(window_bounds.top) <= center_y <= int(window_bounds.bottom)
        except (AttributeError, COMError, TypeError, ValueError):
            return False

    @staticmethod
    def _control_center(control: object) -> tuple[int, int]:
        try:
            bounds = control.BoundingRectangle
            left = int(bounds.left)
            top = int(bounds.top)
            right = int(bounds.right)
            bottom = int(bounds.bottom)
        except (AttributeError, COMError) as exc:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleの操作対象の位置を取得できませんでした",
            ) from exc
        if right <= left or bottom <= top:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleの操作対象の位置が不正です",
            )
        return ((left + right) // 2, (top + bottom) // 2)

    def _click_control(self, control: object) -> None:
        pyautogui.click(*self._control_center(control))

    @staticmethod
    def _activate_control_with_keyboard(control: object) -> None:
        try:
            control.SetFocus()
        except (AttributeError, COMError) as exc:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleの操作対象へフォーカスを設定できませんでした",
            ) from exc
        pyautogui.press("enter")

    @staticmethod
    def _toggle_is_on(control: object) -> bool:
        try:
            state = control.Element.GetCurrentPropertyValue(
                auto.PropertyId.ToggleToggleStateProperty
            )
        except (AttributeError, COMError, TypeError, ValueError):
            return False
        return int(state) == auto.ToggleState.On
