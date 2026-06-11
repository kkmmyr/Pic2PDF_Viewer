import sys
import os
import time
import numpy as np
import cv2
from dataclasses import dataclass
from typing import Tuple, List

# Add parent directory to path to import ocr module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from capturer import AutoKindleCapturer, AutoConfig, KindleCapturer

# プロジェクトルートの .env を読み込む（存在しない場合・dotenv 未インストール時は無視）
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))
except ImportError:
    pass


def _resolve_images_dir() -> str:
    """画像出力先を解決する。優先順:
    1. env KINDLE_NOVEL_IMAGES_DIR（明示指定）
    2. env PIC2PDF_DATA_DIR/kindle_novel/images（OneDrive 等の共有場所）
    3. <repo>/backend/data/kindle_novel/images（ローカルデフォルト）
    """
    if val := os.environ.get("KINDLE_NOVEL_IMAGES_DIR"):
        return val
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.environ.get("PIC2PDF_DATA_DIR")
    if data_dir:
        return os.path.join(data_dir, "kindle_novel", "images")
    return os.path.abspath(os.path.join(base_dir, '..', 'backend', 'data', 'kindle_novel', 'images'))


@dataclass
class NovelConfig(AutoConfig):
    """小説用設定 (白背景前提)"""
    # 白背景判定の閾値 (RGB各値がこれ以上なら白とみなす)
    WHITE_THRESHOLD: int = 240

    # 画像出力先（env KINDLE_NOVEL_IMAGES_DIR で上書き可。backend と同じ env を参照）
    IMG_OUTPUT_DIR: str = _resolve_images_dir()

class NovelKindleCapturer(AutoKindleCapturer):
    """小説用キャプチャクラス (白背景検出 + OCR)"""

    def __init__(self):
        super().__init__()
        self.config = NovelConfig()
        self.ocr = None

    def initialize(self):
        # No OCR init needed
        pass

    def _detect_boundaries(self, img: np.ndarray, w: int, h: int):
        """
        全画面画像からコンテンツ領域（文字領域）を検出する
        白背景(>WHITE_THRESHOLD)の中から、非白画素(文字)がある範囲を探す
        """
        # 上下は固定値 (フルスクリーン設定に従う)
        self.config.CROP_Y1 = self.config.FULLSCREEN_CROP_TOP
        self.config.CROP_Y2 = h - self.config.FULLSCREEN_CROP_BOTTOM_MARGIN

        # --- X-Axis Detection (Left/Right) ---
        # スキャンラインを増やす (10点)
        num_points = 10
        scan_y_list = np.linspace(h * 0.05, h * 0.95, num_points, dtype=int)

        left_edges = []
        right_edges = []

        offset_x = self.config.SIDE_IGNORE_PX

        print(f"Scanning for X-boundaries at Y={scan_y_list}, Offset={offset_x} (White Threshold={self.config.WHITE_THRESHOLD})")

        for y in scan_y_list:
            row = img[y]
            # 白画素判定: すべてのチャンネルが閾値以上
            is_white = np.all(row >= self.config.WHITE_THRESHOLD, axis=1)

            # 左端検出 (左から走査して初めて白でない＝文字が現れる場所)
            left = offset_x
            for x in range(offset_x, w):
                if not is_white[x]: # 文字発見
                    left = x
                    break
            left_edges.append(left)

            # 右端検出
            right = w - offset_x
            for x in range(w - 1 - offset_x, -1, -1):
                if not is_white[x]: # 文字発見
                    right = x
                    break
            right_edges.append(right)

        # 最も外側の値を採用 (文字領域の最大包含)
        final_left = min(left_edges)
        final_right = max(right_edges)

        # マージン適用 (文字ギリギリだと窮屈なので、少し広げる)
        # DETECTION_MARGIN は正の値だと内側(狭くなる)ので、負にして広げるか、定数を調整する
        # ここでは文字の周りに余白を持たせるため、少し外側へ
        PADDING = 10
        self.config.CROP_X1 = max(0, final_left - PADDING)
        self.config.CROP_X2 = min(w, final_right + PADDING)

        print(f"Novel Scan results (Left): {left_edges} -> Selected: {final_left}")
        print(f"Novel Scan results (Right): {right_edges} -> Selected: {final_right}")
        print(f"Detected boundaries: Left={self.config.CROP_X1}, Right={self.config.CROP_X2}")

        if self.config.CROP_X1 >= self.config.CROP_X2:
            print("Warning: Detected invalid boundaries. Using full width.")
            self.config.CROP_X1 = 0
            self.config.CROP_X2 = w

    # _perform_ocr_and_save removed

    def capture_loop(self, title: str) -> Tuple[int, str]:
        # Override capture_loop to inject OCR
        save_dir = os.path.join(self.config.IMG_OUTPUT_DIR, title)
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        # No OCR/PDF Init

        if self.hwnd:
            from ctypes import windll
            windll.user32.SetForegroundWindow(self.hwnd)
            time.sleep(1.0)

        page = 1
        old_image = None

        while True:
            filename = os.path.join(save_dir, f"{page:03d}.png")
            start_time = time.perf_counter()

            while True:
                time.sleep(self.config.WAIT_SEC)
                current_image = self._capture_screen()

                if old_image is None:
                    break

                if not np.array_equal(old_image, current_image):
                    break

                if time.perf_counter() - start_time > self.config.TIMEOUT_SEC:
                    print("Timeout: Page did not change.")
                    # Save PDF before returning
                    return page - 1, save_dir

            # 画像保存
            self._save_image(current_image, filename)

            # OCR Removed
            # PDF Removed

            print(f'Page: {page}, {current_image.shape}, {time.perf_counter() - start_time:.2f} sec')

            old_image = current_image
            page += 1
            self._next_page()
