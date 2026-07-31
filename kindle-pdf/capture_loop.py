import os
import os.path as osp
import time
from collections.abc import Callable
from ctypes import windll
from typing import Optional, Tuple

import cv2
import numpy as np
import pyautogui as pag
from PIL import ImageGrab


class CaptureLoopMixin:
    def _capture_screen(self) -> np.ndarray:
        """現在の設定範囲でスクリーンショットを取得"""
        capture_left = self.rect.left + self.config.CROP_X1
        capture_top = self.rect.top + self.config.CROP_Y1
        capture_right = self.rect.left + self.config.CROP_X2
        capture_bottom = self.rect.top + self.config.CROP_Y2

        image = ImageGrab.grab(
            bbox=(capture_left, capture_top, capture_right, capture_bottom),
            all_screens=True,
        )
        return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

    def _save_image(self, image: np.ndarray, filepath: str):
        """画像を保存 (日本語パス対応)"""
        try:
            is_success, im_buf_arr = cv2.imencode(".png", image)
            if is_success:
                im_buf_arr.tofile(filepath)
            else:
                print(f"Failed to encode image: {filepath}")
        except Exception as e:
            print(f"Failed to save image {filepath}: {e}")

    def _turn_page(self, key: str) -> None:
        """指定したキーでページめくり操作を行う。"""
        if self.hwnd:
            windll.user32.SetForegroundWindow(self.hwnd)
            time.sleep(0.1)
            if int(windll.user32.GetForegroundWindow() or 0) != int(self.hwnd):
                raise RuntimeError(
                    "Kindle window is not foreground before the page turn."
                )
            if self._new_kindle_mode and self._reading_area_relative is not None:
                if self.rect is None:
                    raise RuntimeError("Kindle window rectangle is unavailable.")
                left, top, right, bottom = self._reading_area_relative
                focus_x = self.rect.left + (left + right) // 2
                focus_y = self.rect.top + (top + bottom) // 2
                pag.click(focus_x, focus_y)
                time.sleep(0.1)
                if int(windll.user32.GetForegroundWindow() or 0) != int(self.hwnd):
                    raise RuntimeError(
                        "Kindle window lost foreground while restoring reading focus."
                    )
        pag.keyDown(key)
        time.sleep(0.1)
        pag.keyUp(key)
        time.sleep(self.config.PAGE_TURN_WAIT)

    def _next_page(self) -> None:
        """通常のページ送り方向でページをめくる。"""
        self._turn_page(self.config.PAGE_CHANGE_KEY)

    def _next_page_retry(self) -> None:
        """Store版のキー無反応時だけ、ReadingArea相対の矢印をクリックする。"""
        if not self._new_kindle_mode or self._reading_area_relative is None:
            self._next_page()
            return
        if self.rect is None or not self.hwnd:
            raise RuntimeError("Kindle ReadingArea is unavailable for page retry.")
        windll.user32.SetForegroundWindow(self.hwnd)
        time.sleep(0.1)
        if int(windll.user32.GetForegroundWindow() or 0) != int(self.hwnd):
            raise RuntimeError("Kindle window is not foreground before page retry.")
        left, top, right, bottom = self._reading_area_relative
        page_x = left + 120 if self.config.PAGE_CHANGE_KEY == "left" else right - 120
        page_y = (top + bottom) // 2
        pag.click(self.rect.left + page_x, self.rect.top + page_y)
        time.sleep(self.config.PAGE_TURN_WAIT)

    def _next_page_opposite(self) -> None:
        """通常と反対の方向でページをめくる。"""
        opposite_key = "right" if self.config.PAGE_CHANGE_KEY == "left" else "left"
        self._turn_page(opposite_key)

    def _images_visually_equal(
        self,
        left: np.ndarray,
        right: np.ndarray,
    ) -> bool:
        if left.shape != right.shape:
            return False
        absolute_difference = cv2.absdiff(left, right)
        channel_means = cv2.mean(absolute_difference)[:3]
        mean_difference = sum(channel_means) / len(channel_means)
        if mean_difference >= self.config.PAGE_VISUAL_DIFF_THRESHOLD:
            return False
        gray_difference = cv2.cvtColor(absolute_difference, cv2.COLOR_BGR2GRAY)
        changed_ratio = float(
            np.mean(gray_difference > self.config.PAGE_VISUAL_PIXEL_THRESHOLD)
        )
        return changed_ratio < self.config.PAGE_VISUAL_CHANGED_RATIO_THRESHOLD

    def _wait_for_stable_page(
        self, previous_image: Optional[np.ndarray]
    ) -> Optional[np.ndarray]:
        """ページ変化後、画像が一定時間同一になるまで待つ。"""
        start_time = time.perf_counter()
        candidate = None
        stable_since = None
        saw_change = previous_image is None

        while time.perf_counter() - start_time <= self.config.TIMEOUT_SEC:
            time.sleep(self.config.WAIT_SEC)
            current_image = self._capture_screen()
            now = time.perf_counter()

            if previous_image is not None and self._images_visually_equal(
                previous_image,
                current_image,
            ):
                if not saw_change:
                    continue
                candidate = None
                stable_since = None
                continue

            saw_change = True
            if candidate is not None and self._images_visually_equal(
                candidate,
                current_image,
            ):
                if now - stable_since >= self.config.PAGE_STABLE_SEC:
                    return current_image
                continue

            candidate = current_image
            stable_since = now

        if saw_change:
            raise RuntimeError(
                "Page changed but did not become stable before the timeout."
            )
        return None

    def capture_loop(
        self,
        title: str,
        on_page: Callable[[int], None] | None = None,
    ) -> Tuple[int, str]:
        """キャプチャのメインループ"""
        save_dir = osp.join(self.config.IMG_OUTPUT_DIR, title)
        if not osp.exists(save_dir):
            os.makedirs(save_dir)

        print(f"Saving images to: {save_dir}")

        windll.user32.SetForegroundWindow(self.hwnd)
        time.sleep(1.0)

        page = 1
        old_image = None

        while True:
            filename = osp.join(save_dir, f"{page:03d}.png")
            start_time = time.perf_counter()

            current_image = self._wait_for_stable_page(old_image)
            retry_count = 0
            while (
                current_image is None
                and retry_count < self.config.PAGE_CHANGE_RETRY_COUNT
            ):
                retry_count += 1
                print(
                    "Page did not change; retrying page turn "
                    f"({retry_count}/{self.config.PAGE_CHANGE_RETRY_COUNT})."
                )
                self._next_page_retry()
                current_image = self._wait_for_stable_page(old_image)

            if current_image is None and page == 2:
                print(
                    "First page did not advance with the selected key; "
                    "trying the opposite key once."
                )
                self._next_page_opposite()
                current_image = self._wait_for_stable_page(old_image)

            if current_image is None:
                captured_pages = page - 1
                if (
                    self.config.EXPECTED_PAGES is not None
                    and captured_pages < self.config.EXPECTED_PAGES
                ):
                    raise RuntimeError(
                        "Capture stopped before the expected count: "
                        f"{captured_pages}/{self.config.EXPECTED_PAGES}."
                    )
                print("End of book: Page did not change.")
                return captured_pages, save_dir

            self._save_image(current_image, filename)
            if on_page is not None:
                on_page(page)
            print(
                f"Page: {page}, {current_image.shape}, "
                f"{time.perf_counter() - start_time:.2f} sec"
            )

            if (
                self.config.EXPECTED_PAGES is not None
                and page >= self.config.EXPECTED_PAGES
            ):
                print(f"Reached expected capture count: {page}")
                return page, save_dir

            old_image = current_image
            page += 1
            self._next_page()
