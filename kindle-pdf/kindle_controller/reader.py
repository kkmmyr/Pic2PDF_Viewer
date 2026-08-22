import logging
import time
from collections.abc import Callable

from PIL import Image
from kindle_platform import COMError, pyautogui

from .models import (
    KindleControllerError,
    footer_indicates_cover,
    footer_indicates_start,
)
from .reader_policy import needs_cover_step, page_layout_policy, previous_page_key
from .reader_ui import ReaderUIAdapter
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
        policy = page_layout_policy(source)
        if policy is None:
            raise KindleControllerError(
                "positioning_failed",
                "Kindleのページレイアウト種別が不正です",
            )
        ReaderUIAdapter(self).apply_page_layout(policy)

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
        try:
            return self._run_location_start_workflow(
                source=source,
                direction=direction,
                on_poll=on_poll,
            )
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

    def _run_location_start_workflow(
        self,
        *,
        source: str,
        direction: str,
        on_poll: Callable[[], None] | None,
    ) -> bool:
        adapter = ReaderUIAdapter(self)
        try:
            self._ensure_process_running()
            if on_poll:
                on_poll()
            if not adapter.open_location_dialog():
                return False
            if not adapter.set_location_value("1") or not adapter.confirm_location():
                return False
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
            if needs_cover_step(source, footer_name) and not self._step_back_to_cover(
                source=source,
                direction=direction,
                on_poll=on_poll,
                adapter=adapter,
            ):
                return False
            if on_poll:
                on_poll()
            return True
        finally:
            adapter.dismiss_location_dialog()

    def _step_back_to_cover(
        self,
        *,
        source: str,
        direction: str,
        on_poll: Callable[[], None] | None,
        adapter: ReaderUIAdapter,
    ) -> bool:
        if not adapter.show_chrome():
            return False
        adapter.press_key(previous_page_key(direction))
        self.wait_for_reader_stable()
        return (
            self._wait_for_start_footer(
                source,
                cover_only=True,
                on_poll=on_poll,
            )
            is not None
        )

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
        if not needs_cover_step(source, footer_name or ""):
            return False
        reading_area = self._control_by_id("ReadingArea", timeout=1.0)
        if reading_area is None:
            return False
        self._click_control(reading_area)
        time.sleep(0.25)
        pyautogui.press(previous_page_key(direction))
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
