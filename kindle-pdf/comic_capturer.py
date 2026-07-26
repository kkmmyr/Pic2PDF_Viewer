import time
from collections.abc import Callable
from ctypes import POINTER, Structure, c_void_p, pointer, sizeof, windll
from ctypes import wintypes
from ctypes.wintypes import RECT
from dataclasses import dataclass

import numpy as np
import pyautogui as pag
from PIL import ImageGrab

from capture_base import Config, KindleCapturer


@dataclass
class AutoConfig(Config):
    """メイン設定を継承し、自動検出用の設定を追加"""

    FULLSCREEN_CROP_TOP: int = 0
    FULLSCREEN_CROP_BOTTOM_MARGIN: int = 0
    FULLSCREEN_SETTLE_SEC: float = 5.0
    NEW_KINDLE_SETTLE_SEC: float = 2.0
    NEW_KINDLE_CROP_TOP: int = 56
    NEW_KINDLE_CROP_BOTTOM_MARGIN: int = 8
    NEW_KINDLE_SIDE_IGNORE_PX: int = 180
    BLACK_THRESHOLD: int = 20
    DETECTION_MARGIN: int = 0
    SIDE_IGNORE_PX: int = 500
    CAPTURE_SPREAD: bool = False
    COMIC_WHITE_THRESHOLD: int = 245
    COMIC_MIN_PAGE_ASPECT_RATIO: float = 0.68
    COMIC_SPREAD_DETECTION_RATIO: float = 1.1
    COMIC_SPREAD_PADDING_PX: int = 16


class AutoKindleCapturer(KindleCapturer):
    """フルスクリーン・動的クロップ版キャプチャクラス"""

    def __init__(self):
        super().__init__()
        self.config = AutoConfig()
        self._reading_area_relative: tuple[int, int, int, int] | None = None

    def _is_fullscreen(self) -> bool:
        """対象ウィンドウが配置先モニター全体を覆っているか判定する。"""
        if not self.hwnd:
            return False

        class MonitorInfo(Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", RECT),
                ("rcWork", RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        monitor_from_window = windll.user32.MonitorFromWindow
        monitor_from_window.argtypes = [c_void_p, wintypes.DWORD]
        monitor_from_window.restype = c_void_p
        monitor = monitor_from_window(
            c_void_p(self.hwnd),
            2,
        )
        if not monitor:
            return False

        info = MonitorInfo()
        info.cbSize = sizeof(MonitorInfo)
        get_monitor_info = windll.user32.GetMonitorInfoW
        get_monitor_info.argtypes = [c_void_p, POINTER(MonitorInfo)]
        get_monitor_info.restype = wintypes.BOOL
        if not get_monitor_info(monitor, pointer(info)):
            return False

        rect = self._get_window_rect()
        monitor_rect = info.rcMonitor
        tolerance = 2
        return (
            abs(rect.left - monitor_rect.left) <= tolerance
            and abs(rect.top - monitor_rect.top) <= tolerance
            and abs(rect.right - monitor_rect.right) <= tolerance
            and abs(rect.bottom - monitor_rect.bottom) <= tolerance
        )

    def setup_window(
        self,
        reading_area_bounds_provider: Callable[[], tuple[int, int, int, int]]
        | None = None,
    ):
        """Kindle版に応じて最大化またはフルスクリーンに設定する。"""
        if not self.hwnd:
            raise RuntimeError("Window handle not found. Call find_window() first.")

        windll.user32.SetForegroundWindow(self.hwnd)
        time.sleep(0.5)

        self._new_kindle_mode = self._get_window_title() == "Kindle"

        if self._new_kindle_mode:
            if self._is_fullscreen() and not windll.user32.IsZoomed(self.hwnd):
                self._restore_fullscreen_on_cleanup = True
                pag.press("f11")
                time.sleep(1.0)

            if windll.user32.IsZoomed(self.hwnd):
                print("Kindle is already maximized.")
            else:
                windll.user32.ShowWindow(self.hwnd, 3)
                self._maximized_window = True
                print("Maximizing Microsoft Store Kindle window...")

            self.config.FULLSCREEN_CROP_TOP = self.config.NEW_KINDLE_CROP_TOP
            self.config.FULLSCREEN_CROP_BOTTOM_MARGIN = (
                self.config.NEW_KINDLE_CROP_BOTTOM_MARGIN
            )
            self.config.SIDE_IGNORE_PX = self.config.NEW_KINDLE_SIDE_IGNORE_PX
            time.sleep(self.config.NEW_KINDLE_SETTLE_SEC)
        elif self._is_fullscreen():
            print("Kindle is already in fullscreen mode.")
        else:
            pag.press("f11")
            self._entered_fullscreen = True
            print("Entering fullscreen mode...")
            time.sleep(self.config.FULLSCREEN_SETTLE_SEC)

        self.rect = self._get_window_rect()
        screen_w = self.rect.right - self.rect.left
        screen_h = self.rect.bottom - self.rect.top
        if screen_w <= 0 or screen_h <= 0:
            raise RuntimeError("Kindle window has an invalid size.")

        self._reading_area_relative = (
            0,
            self.config.FULLSCREEN_CROP_TOP,
            screen_w,
            screen_h - self.config.FULLSCREEN_CROP_BOTTOM_MARGIN,
        )
        if self._new_kindle_mode and reading_area_bounds_provider is not None:
            self._apply_reading_area_bounds(
                reading_area_bounds_provider(),
                screen_w,
                screen_h,
            )
            self._focus_reading_area()

        print("Detecting content boundaries...")
        full_img = ImageGrab.grab(
            bbox=(self.rect.left, self.rect.top, self.rect.right, self.rect.bottom),
            all_screens=True,
        )
        img_np = np.array(full_img)

        self._detect_boundaries(img_np, screen_w, screen_h)

        if self._new_kindle_mode:
            safe_x = self.rect.left + screen_w // 2
            safe_y = self.rect.top + max(10, self.config.CROP_Y1 // 2)
        else:
            safe_x = self.rect.left + min(self.config.CROP_X2 + 50, screen_w - 10)
            safe_y = self.rect.top + screen_h // 2
        pag.moveTo(safe_x, safe_y)
        print(f"Mouse moved to safe area: ({safe_x}, {safe_y})")

    def _focus_reading_area(self) -> None:
        """最大化後の読書領域へキーボードフォーカスを戻す。"""
        if self.rect is None or self._reading_area_relative is None:
            raise RuntimeError("Kindle ReadingArea is unavailable.")
        left, top, right, bottom = self._reading_area_relative
        center_x = self.rect.left + (left + right) // 2
        center_y = self.rect.top + (top + bottom) // 2
        pag.click(center_x, center_y)
        time.sleep(0.5)
        print(f"Focused Kindle ReadingArea: ({center_x}, {center_y})")

    def _apply_reading_area_bounds(
        self,
        bounds: tuple[int, int, int, int],
        w: int,
        h: int,
    ) -> None:
        """画面座標のReadingAreaをウィンドウ相対クロップへ変換する。"""
        if self.rect is None:
            raise RuntimeError("Kindle window rectangle is unavailable.")
        left, top, right, bottom = bounds
        relative = (
            max(0, min(w, left - self.rect.left)),
            max(0, min(h, top - self.rect.top)),
            max(0, min(w, right - self.rect.left)),
            max(0, min(h, bottom - self.rect.top)),
        )
        if relative[0] >= relative[2] or relative[1] >= relative[3]:
            raise RuntimeError("Kindle ReadingArea has an invalid size.")

        self._reading_area_relative = relative
        self.config.FULLSCREEN_CROP_TOP = relative[1]
        self.config.FULLSCREEN_CROP_BOTTOM_MARGIN = h - relative[3]
        print(
            "Using Kindle ReadingArea: "
            f"Left={relative[0]}, Top={relative[1]}, "
            f"Right={relative[2]}, Bottom={relative[3]}"
        )

    def _detect_boundaries(self, img: np.ndarray, w: int, h: int):
        """複数行を走査し、コンテンツ領域をconfigへ反映する。"""
        self.config.CROP_Y1 = self.config.FULLSCREEN_CROP_TOP
        self.config.CROP_Y2 = h - self.config.FULLSCREEN_CROP_BOTTOM_MARGIN

        if self.config.CAPTURE_SPREAD:
            self._detect_spread_boundaries(img, w)
            return

        scan_y_list = [h // 4, h // 2, (h * 3) // 4]
        left_edges = []
        right_edges = []
        offset = self.config.SIDE_IGNORE_PX

        print(f"Scanning for boundaries at Y={scan_y_list}, Offset={offset}")

        for y in scan_y_list:
            row = img[y]
            is_black = np.all(row <= self.config.BLACK_THRESHOLD, axis=1)

            left = offset
            for x in range(offset, w):
                if not is_black[x]:
                    left = x
                    break
            left_edges.append(left)

            right = w - offset
            for x in range(w - 1 - offset, -1, -1):
                if not is_black[x]:
                    right = x
                    break
            right_edges.append(right)

        final_left = min(left_edges)
        final_right = max(right_edges)

        self.config.CROP_X1 = final_left + self.config.DETECTION_MARGIN
        self.config.CROP_X2 = final_right - self.config.DETECTION_MARGIN

        print(f"Scan results (Left): {left_edges} -> Selected: {final_left}")
        print(f"Scan results (Right): {right_edges} -> Selected: {final_right}")
        print(
            f"Detected boundaries: Left={self.config.CROP_X1}, "
            f"Right={self.config.CROP_X2}"
        )

        if self.config.CROP_X1 >= self.config.CROP_X2:
            print("Warning: Detected invalid boundaries. Using full width.")
            self.config.CROP_X1 = 0
            self.config.CROP_X2 = w

    def _detect_spread_boundaries(self, img: np.ndarray, w: int) -> None:
        """先頭の単ページから、後続2ページを切らない中央安全幅を決める。"""
        if self._reading_area_relative is None:
            reading_left = 0
            reading_right = w
        else:
            reading_left, _, reading_right, _ = self._reading_area_relative

        y1 = self.config.CROP_Y1
        y2 = self.config.CROP_Y2
        region = img[y1:y2, reading_left:reading_right]
        if region.size == 0:
            raise RuntimeError("Kindle comic reading area is empty.")

        non_white = np.any(region < self.config.COMIC_WHITE_THRESHOLD, axis=2)
        minimum_pixels = max(3, int(region.shape[0] * 0.002))
        active_columns = np.flatnonzero(
            np.count_nonzero(non_white, axis=0) >= minimum_pixels
        )
        reading_width = reading_right - reading_left
        if active_columns.size == 0:
            print(
                "Warning: Comic page width was not detected; "
                "using the full ReadingArea."
            )
            self.config.CROP_X1 = reading_left
            self.config.CROP_X2 = reading_right
            return

        detected_left = reading_left + int(active_columns[0])
        detected_right = reading_left + int(active_columns[-1]) + 1
        detected_width = detected_right - detected_left
        content_height = y2 - y1
        minimum_page_width = int(
            content_height * self.config.COMIC_MIN_PAGE_ASPECT_RATIO
        )
        padding = self.config.COMIC_SPREAD_PADDING_PX

        if detected_width >= content_height * self.config.COMIC_SPREAD_DETECTION_RATIO:
            target_width = detected_width + padding * 2
        else:
            page_width = max(detected_width, minimum_page_width)
            target_width = page_width * 2 + padding * 2
        target_width = min(reading_width, target_width)

        center = (reading_left + reading_right) // 2
        crop_left = max(reading_left, center - target_width // 2)
        crop_right = min(reading_right, crop_left + target_width)
        crop_left = max(reading_left, crop_right - target_width)
        self.config.CROP_X1 = crop_left
        self.config.CROP_X2 = crop_right
        print(
            "Detected comic spread boundaries: "
            f"page=({detected_left}, {detected_right}), "
            f"crop=({crop_left}, {crop_right})"
        )

    def cleanup(self):
        """終了処理: ツールが変更した表示状態だけ元へ戻す。"""
        if self.hwnd and self._maximized_window:
            windll.user32.ShowWindow(self.hwnd, 9)
            time.sleep(1.0)
            print("Restored Kindle window size.")
            self._maximized_window = False

        if self.hwnd and self._restore_fullscreen_on_cleanup:
            windll.user32.SetForegroundWindow(self.hwnd)
            time.sleep(0.5)
            pag.press("f11")
            time.sleep(1.0)
            print("Restored Kindle fullscreen mode.")
            self._restore_fullscreen_on_cleanup = False

        if self.hwnd and self._entered_fullscreen:
            windll.user32.SetForegroundWindow(self.hwnd)
            time.sleep(0.5)
            if self._is_fullscreen():
                pag.press("f11")
                time.sleep(1.0)
                print("Exited fullscreen mode.")
            self._entered_fullscreen = False
