import logging
import time
from _ctypes import COMError
from collections.abc import Callable

import pyautogui
from PIL import Image

from .models import (
    KindleControllerError,
    footer_indicates_cover,
    footer_indicates_start,
    novel_footer_indicates_first_page,
)
from .window import WindowController

logger = logging.getLogger(__name__)


class ReaderControllerMixin(WindowController):
    def reading_area_bounds(self) -> tuple[int, int, int, int]:
        """現在のReadingAreaを画面座標で返す。"""
        reading_area = self._control_by_id("ReadingArea", timeout=2.0)
        if reading_area is None:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleの読書領域を取得できませんでした",
            )
        try:
            bounds = reading_area.BoundingRectangle
            result = (
                int(bounds.left),
                int(bounds.top),
                int(bounds.right),
                int(bounds.bottom),
            )
        except (AttributeError, COMError, TypeError, ValueError) as exc:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleの読書領域の位置を取得できませんでした",
            ) from exc
        if result[0] >= result[2] or result[1] >= result[3]:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleの読書領域の位置が不正です",
            )
        return result

    def capture_area_bounds(self, source: str) -> tuple[int, int, int, int]:
        """source別に保存対象となる読書領域を画面座標で返す。"""
        reading_left, reading_top, reading_right, reading_bottom = (
            self.reading_area_bounds()
        )
        if source == "comic":
            return (reading_left, reading_top, reading_right, reading_bottom)
        if source != "novel":
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleの撮影領域種別が不正です",
            )

        top_chrome = self._control_by_id("TopChrome", timeout=2.0)
        footer = self._control_by_id("Footer", timeout=2.0)
        if top_chrome is None or footer is None:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleの小説本文領域を取得できませんでした",
            )
        try:
            content_top = int(top_chrome.BoundingRectangle.bottom)
            content_bottom = int(footer.BoundingRectangle.top)
        except (AttributeError, COMError, TypeError, ValueError) as exc:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleの小説本文領域の位置を取得できませんでした",
            ) from exc
        if not (reading_top <= content_top < content_bottom <= reading_bottom):
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "Kindleの小説本文領域の位置が不正です",
            )
        return (reading_left, content_top, reading_right, content_bottom)

    def set_page_layout(self, source: str) -> None:
        """comicは2ページ、novelは1ページを選択して状態を検証する。"""
        option_ids = {
            "comic": "aaOption-Split",
            "novel": "aaOption-Single",
        }
        option_id = option_ids.get(source)
        if option_id is None:
            raise KindleControllerError(
                "positioning_failed",
                "Kindleのページレイアウト種別が不正です",
            )

        reading_area = self._control_by_id("ReadingArea", timeout=2.0)
        if reading_area is None:
            raise KindleControllerError(
                "positioning_failed",
                "Kindleの読書領域を取得できませんでした",
            )
        page_settings = self._control_by_id("aaMenuButton", timeout=0.5)
        if page_settings is None:
            self._click_control(reading_area)
            time.sleep(0.5)
            page_settings = self._control_by_id("aaMenuButton", timeout=2.0)
        if page_settings is None:
            raise KindleControllerError(
                "positioning_failed",
                "Kindleのページ設定を開けませんでした",
            )

        menu_opened = False
        try:
            self._click_control(page_settings)
            menu_opened = True
            time.sleep(0.5)
            option = self._control_by_id(option_id, timeout=2.0)
            if option is None:
                if (
                    source == "novel"
                    and self._control_by_id("フォント-item", timeout=1.0) is not None
                ):
                    return
                raise KindleControllerError(
                    "positioning_failed",
                    "Kindleのページレイアウトを取得できませんでした",
                )
            if not self._toggle_is_on(option):
                self._click_control(option)

            deadline = time.monotonic() + self.config.control_timeout_seconds
            while time.monotonic() < deadline:
                option = self._control_by_id(option_id, timeout=0.5)
                if option is not None and self._toggle_is_on(option):
                    return
                time.sleep(0.25)
            raise KindleControllerError(
                "positioning_failed",
                "Kindleのページレイアウトを確認できませんでした",
            )
        finally:
            if menu_opened:
                close_button = self._control_by_id(
                    "CloseSideMenuHeaderButton",
                    timeout=1.0,
                )
                if close_button is not None:
                    self._click_control(close_button)
                else:
                    pyautogui.press("esc")
                time.sleep(0.25)
            if self._control_by_id("aaMenuButton", timeout=0.5) is not None:
                reading_area = self._control_by_id("ReadingArea", timeout=1.0)
                if reading_area is not None:
                    self._click_control(reading_area)
                    time.sleep(0.25)

    def _reading_area_image(self, *, timeout: float = 1.0) -> Image.Image | None:
        reading_area = self._control_by_id("ReadingArea", timeout=timeout)
        if reading_area is None:
            return None
        bounds = reading_area.BoundingRectangle
        width = int(bounds.right - bounds.left)
        height = int(bounds.bottom - bounds.top)
        if width <= 0 or height <= 0:
            return None
        try:
            return pyautogui.screenshot(
                region=(int(bounds.left), int(bounds.top), width, height)
            )
        except OSError:
            logger.exception("Kindle reading area screenshot failed")
            return None

    def _try_go_to_location_start(
        self,
        source: str,
        *,
        direction: str = "left",
        on_poll: Callable[[], None] | None = None,
    ) -> bool:
        """「位置に移動」で先頭へ移動し、source別フッターで検証する。"""
        ui_opened = False
        verified = False
        try:
            self._ensure_process_running()
            if on_poll:
                on_poll()

            reading_area = self._control_by_id("ReadingArea", timeout=1.0)
            if reading_area is None:
                return False
            more_menu = self._button_by_id("moreMenuButton", timeout=0.5)
            if more_menu is None:
                self._click_control(reading_area)
                time.sleep(0.25)
                more_menu = self._button_by_id("moreMenuButton", timeout=1.0)
            if more_menu is None:
                return False

            self._click_control(more_menu)
            ui_opened = True
            time.sleep(0.25)
            # The Store app exposes this popover through a separate UIA root and
            # its item rectangle is intermittent. The first item stays anchored
            # to the verified menu button; the typed edit appearing afterwards
            # is the safety proof that the intended item was selected.
            if not self._click_relative_to_control(
                more_menu,
                x_offset=-30,
                y_offset=45,
            ):
                return False
            time.sleep(0.25)

            location_input = self._edit_by_id(
                "go-to-page-input",
                timeout=1.0,
            )
            if location_input is None:
                return False
            try:
                value_pattern = location_input.GetValuePattern()
                value_pattern.SetValue("1")
                time.sleep(0.1)
                raw_input_value = value_pattern.Value
                input_value = None if raw_input_value is None else str(raw_input_value)
            except (AttributeError, COMError, TypeError, ValueError):
                input_value = None
            if input_value != "1":
                return False

            confirm = self._button_by_id("modal-confirm", timeout=1.0)
            if confirm is None:
                return False
            self._click_control(confirm)
            for _attempt in range(20):
                if self._edit_by_id("go-to-page-input", timeout=0.25) is None:
                    break
                time.sleep(0.1)
            else:
                return False
            ui_opened = False
            if on_poll:
                on_poll()
            self.wait_for_reader_stable()

            footer_name = self._wait_for_start_footer(
                source,
                cover_only=False,
                on_poll=on_poll,
            )
            if footer_name is None:
                return False
            if source == "novel" and novel_footer_indicates_first_page(footer_name):
                reading_area = self._control_by_id("ReadingArea", timeout=1.0)
                if reading_area is None:
                    return False
                self._click_control(reading_area)
                time.sleep(0.25)
                previous_page_key = "right" if direction == "left" else "left"
                pyautogui.press(previous_page_key)
                self.wait_for_reader_stable()
                footer_name = self._wait_for_start_footer(
                    source,
                    cover_only=True,
                    on_poll=on_poll,
                )
                if footer_name is None:
                    return False
            verified = True
            if on_poll:
                on_poll()
            return verified
        except KindleControllerError as exc:
            if exc.error_code == "kindle_app_exited":
                raise
            logger.info(
                "Kindle direct location jump unavailable: %s",
                exc,
            )
            return False
        except (AttributeError, COMError, OSError, TypeError, ValueError):
            logger.info(
                "Kindle direct location jump failed",
                exc_info=True,
            )
            return False
        finally:
            if ui_opened and not verified:
                pyautogui.press("esc")
                time.sleep(0.1)

    def _wait_for_start_footer(
        self,
        source: str,
        *,
        cover_only: bool,
        on_poll: Callable[[], None] | None,
    ) -> str | None:
        """直接遷移後のフッターを短時間だけ待ち、必要ならchromeを表示する。"""
        predicate = footer_indicates_cover if cover_only else footer_indicates_start
        chrome_revealed = False
        # ページ本体の描画完了後も FooterLabelText の Name 更新が数秒遅れる
        # 実機例がある。ページ送りは追加せず、同じ control の更新だけを待つ。
        for _attempt in range(12):
            self._ensure_process_running()
            if on_poll:
                on_poll()
            footer = self._control_by_id("FooterLabelText", timeout=0.75)
            footer_name = None if footer is None else str(footer.Name)
            if predicate(source, footer_name):
                return footer_name
            if not chrome_revealed:
                reading_area = self._control_by_id("ReadingArea", timeout=0.75)
                if reading_area is not None:
                    self._click_control(reading_area)
                    chrome_revealed = True
            time.sleep(0.25)
        return None

    def _try_use_current_start(
        self,
        source: str,
        *,
        direction: str,
        on_poll: Callable[[], None] | None,
    ) -> bool:
        try:
            footer = self._control_by_id("FooterLabelText", timeout=1.0)
        except KindleControllerError as exc:
            if exc.error_code == "kindle_app_exited":
                raise
            return False
        footer_name = None if footer is None else str(footer.Name)
        if footer_indicates_cover(source, footer_name):
            return True
        if source != "novel" or not novel_footer_indicates_first_page(footer_name):
            return False
        reading_area = self._control_by_id("ReadingArea", timeout=1.0)
        if reading_area is None:
            return False
        self._click_control(reading_area)
        time.sleep(0.25)
        previous_page_key = "right" if direction == "left" else "left"
        pyautogui.press(previous_page_key)
        self.wait_for_reader_stable()
        return (
            self._wait_for_start_footer(
                source,
                cover_only=True,
                on_poll=on_poll,
            )
            is not None
        )

    def go_to_start(
        self,
        *,
        source: str,
        direction: str,
        on_poll: Callable[[], None] | None = None,
    ) -> None:
        if source not in {"comic", "novel"}:
            raise KindleControllerError(
                "positioning_failed",
                "Kindleの撮影領域種別が不正です",
            )
        if direction not in {"left", "right"}:
            raise KindleControllerError(
                "positioning_failed",
                "ページ送り方向が不正です",
            )
        if self._try_use_current_start(
            source,
            direction=direction,
            on_poll=on_poll,
        ) or self._try_go_to_location_start(
            source,
            direction=direction,
            on_poll=on_poll,
        ):
            return
        raise KindleControllerError(
            "positioning_failed",
            "Kindleの直接ページ遷移または開始位置を確認できませんでした",
        )
