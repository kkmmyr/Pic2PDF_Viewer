import os
import os.path as osp
import time
from collections.abc import Callable

import cv2
import numpy as np
from PIL import ImageGrab

from capture_loop_io import capture_screen, prepare_image_dir, save_png
from capture_loop_models import (
    CaptureProgress,
    CaptureReport,
    CaptureResult,
    build_capture_result,
)
from capture_loop_policy import (
    PageChangeAction,
    capture_stopped_too_early,
    expected_count_reached,
    page_change_recovery_actions,
)
from kindle_platform import pyautogui as pag, windll

_COMPATIBILITY_EXPORTS = (cv2, ImageGrab, CaptureReport, CaptureResult)


class CaptureLoopMixin:
    def _capture_screen(self) -> np.ndarray:
        """現在の設定範囲でスクリーンショットを取得"""
        return capture_screen(self.rect, self.config)

    def _save_image(self, image: np.ndarray, filepath: str) -> None:
        """画像を保存 (日本語パス対応)"""
        save_png(image, filepath)

    def _discard_image(self, filepath: str) -> None:
        """終端周期で保存済みと判明した一時重複画像を破棄する。"""
        os.remove(filepath)

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
        self, previous_image: np.ndarray | None
    ) -> np.ndarray | None:
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

    def _wait_for_page_change(
        self,
        previous_image: np.ndarray | None,
        page: int,
        progress: CaptureProgress,
    ) -> tuple[np.ndarray | None, int, bool]:
        current_image = self._wait_for_stable_page(previous_image)
        if current_image is None:
            progress.unchanged_observation_windows += 1
        retry_count = 0
        opposite_attempted = False
        actions = page_change_recovery_actions(
            page=page,
            retry_limit=self.config.PAGE_CHANGE_RETRY_COUNT,
        )
        for action in actions:
            if current_image is not None:
                break
            if action is PageChangeAction.RETRY_SELECTED:
                retry_count += 1
                print(
                    "Page did not change; retrying page turn "
                    f"({retry_count}/{self.config.PAGE_CHANGE_RETRY_COUNT})."
                )
                self._next_page_retry()
                progress.retry_commands += 1
            else:
                opposite_attempted = True
                print(
                    "First page did not advance with the selected key; "
                    "trying the opposite key once."
                )
                self._next_page_opposite()
                progress.opposite_direction_commands += 1
            progress.turn_commands += 1
            current_image = self._wait_for_stable_page(previous_image)
            if current_image is None:
                progress.unchanged_observation_windows += 1
        return current_image, retry_count, opposite_attempted

    def _confirm_expected_end(
        self, current_image: np.ndarray, progress: CaptureProgress
    ) -> int:
        self._next_page()
        progress.turn_commands += 1
        following_image = self._wait_for_stable_page(current_image)
        if following_image is None:
            progress.unchanged_observation_windows += 1
        retry_count = 0
        while (
            following_image is None
            and retry_count < self.config.PAGE_CHANGE_RETRY_COUNT
        ):
            retry_count += 1
            self._next_page_retry()
            progress.turn_commands += 1
            progress.retry_commands += 1
            following_image = self._wait_for_stable_page(current_image)
            if following_image is None:
                progress.unchanged_observation_windows += 1
        if following_image is not None:
            raise RuntimeError(
                "Expected capture count was reached, but another page exists."
            )
        return retry_count + 1

    def _build_capture_result(
        self,
        save_dir: str,
        captured_pages: int,
        reason: str,
        current_image: np.ndarray,
        termination_windows: int,
        progress: CaptureProgress,
    ) -> CaptureResult:
        height, width = current_image.shape[:2]
        return build_capture_result(
            config=self.config,
            save_dir=save_dir,
            captured_pages=captured_pages,
            reason=reason,
            image_size=(width, height),
            termination_windows=termination_windows,
            progress=progress,
        )

    def capture_loop(
        self,
        title: str,
        on_page: Callable[[int], None] | None = None,
    ) -> CaptureResult:
        """キャプチャのメインループ"""
        save_dir = prepare_image_dir(self.config.IMG_OUTPUT_DIR, title)

        print(f"Saving images to: {save_dir}")

        windll.user32.SetForegroundWindow(self.hwnd)
        time.sleep(1.0)

        page = 1
        old_image = None
        two_pages_back = None
        two_screen_cycle_matches = 0
        progress = CaptureProgress()

        while True:
            filename = osp.join(save_dir, f"{page:03d}.png")
            start_time = time.perf_counter()

            current_image, retry_count, opposite_attempted = self._wait_for_page_change(
                old_image, page, progress
            )

            if current_image is None:
                captured_pages = page - 1
                if capture_stopped_too_early(
                    captured_pages,
                    self.config.EXPECTED_PAGES,
                ):
                    raise RuntimeError(
                        "Capture stopped before the expected count: "
                        f"{captured_pages}/{self.config.EXPECTED_PAGES}."
                    )
                print("End of book: Page did not change.")
                if old_image is None:
                    raise RuntimeError(
                        "Capture ended before the first image was saved."
                    )
                return self._build_capture_result(
                    save_dir,
                    captured_pages,
                    "visual_no_change_after_retries",
                    old_image,
                    retry_count + 1 + int(opposite_attempted),
                    progress,
                )

            if two_pages_back is not None and self._images_visually_equal(
                two_pages_back,
                current_image,
            ):
                two_screen_cycle_matches += 1
            else:
                two_screen_cycle_matches = 0
            if two_screen_cycle_matches >= 2:
                captured_pages = page - 2
                minimum_capture_screens = (
                    10 if getattr(self.config, "CAPTURE_SPREAD", False) else 50
                )
                if (
                    captured_pages >= minimum_capture_screens
                    and not capture_stopped_too_early(
                        captured_pages,
                        self.config.EXPECTED_PAGES,
                    )
                ):
                    duplicate_filename = osp.join(
                        save_dir,
                        f"{page - 1:03d}.png",
                    )
                    self._discard_image(duplicate_filename)
                    progress.unchanged_observation_windows += 2
                    print(
                        "End of book: Kindle repeated the final two screens; "
                        f"discarded {osp.basename(duplicate_filename)}."
                    )
                    return self._build_capture_result(
                        save_dir,
                        captured_pages,
                        "visual_no_change_after_retries",
                        current_image,
                        2,
                        progress,
                    )
                raise RuntimeError(
                    "Capture entered a two-screen cycle; "
                    "check the selected page direction."
                )

            self._save_image(current_image, filename)
            if on_page is not None:
                on_page(page)
            print(
                f"Page: {page}, {current_image.shape}, "
                f"{time.perf_counter() - start_time:.2f} sec"
            )

            if expected_count_reached(page, self.config.EXPECTED_PAGES):
                print(
                    f"Reached expected capture count: {page}; confirming end of book."
                )
                termination_windows = self._confirm_expected_end(
                    current_image, progress
                )
                return self._build_capture_result(
                    save_dir,
                    page,
                    "expected_screen_count_confirmed",
                    current_image,
                    termination_windows,
                    progress,
                )

            two_pages_back = old_image
            old_image = current_image
            page += 1
            self._next_page()
            progress.turn_commands += 1
