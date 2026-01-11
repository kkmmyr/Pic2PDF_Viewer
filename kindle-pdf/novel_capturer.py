import sys
import os
import time
import numpy as np
import cv2
from dataclasses import dataclass
from typing import Tuple, List

# Add parent directory to path to import ocr module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ocr.ocr_engine import get_ocr_engine
from capturer import AutoKindleCapturer, AutoConfig, KindleCapturer

@dataclass
class NovelConfig(AutoConfig):
    """小説用設定 (白背景前提)"""
    # 白背景判定の閾値 (RGB各値がこれ以上なら白とみなす)
    WHITE_THRESHOLD: int = 240
    
    # OCR Engine
    OCR_ENGINE: str = 'yomitoku'

class NovelKindleCapturer(AutoKindleCapturer):
    """小説用キャプチャクラス (白背景検出 + OCR)"""
    
    def __init__(self):
        super().__init__()
        self.config = NovelConfig()
        self.ocr = None
        
    def initialize_ocr(self):
        """OCRエンジンの初期化"""
        print(f"Initializing OCR engine ({self.config.OCR_ENGINE})...")
        try:
            self.ocr = get_ocr_engine(self.config.OCR_ENGINE)
            self.ocr.initialize()
            print("OCR engine initialized.")
        except Exception as e:
            print(f"Failed to initialize OCR engine: {e}")
            raise e

    def _detect_boundaries(self, img: np.ndarray, w: int, h: int):
        """
        全画面画像からコンテンツ領域（文字領域）を検出する
        白背景(>WHITE_THRESHOLD)の中から、非白画素(文字)がある範囲を探す
        """
        # 上下は固定値
        self.config.CROP_Y1 = self.config.FULLSCREEN_CROP_TOP
        self.config.CROP_Y2 = h - self.config.FULLSCREEN_CROP_BOTTOM_MARGIN
        
        scan_y_list = [h // 4, h // 2, (h * 3) // 4]
        
        left_edges = []
        right_edges = []
        
        offset = self.config.SIDE_IGNORE_PX

        print(f"Scanning for TEXT boundaries at Y={scan_y_list}, Offset={offset} (White Threshold={self.config.WHITE_THRESHOLD})")

        for y in scan_y_list:
            row = img[y]
            # 白画素判定: すべてのチャンネルが閾値以上
            is_white = np.all(row >= self.config.WHITE_THRESHOLD, axis=1)
            
            # 左端検出 (左から走査して初めて白でない＝文字が現れる場所)
            left = offset
            for x in range(offset, w):
                if not is_white[x]: # 文字発見
                    left = x
                    break
            left_edges.append(left)
            
            # 右端検出
            right = w - offset
            for x in range(w - 1 - offset, -1, -1):
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

    def _perform_ocr_and_save(self, image: np.ndarray, page_num: int, save_dir: str):
        """OCRを実行してテキストを保存"""
        print(f"[DEBUG] Starting OCR for page {page_num}...")
        if not self.ocr:
            print("[DEBUG] OCR engine is None!")
            return

        try:
            # OCRはRGB画像を期待することが多いが、OpenCVはBGR
            # yomitoku/paddleはRGBを好む場合が多いので変換確認
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = self.ocr.extract_text(image_rgb)
            
            # テキスト抽出
            lines = [item['text'] for item in results]
            text_content = "\n".join(lines)
            print(f"[DEBUG] Extracted {len(lines)} lines. Saving to file...")
            
            txt_filename = os.path.join(save_dir, f"{page_num:03d}.txt")
            with open(txt_filename, "w", encoding="utf-8") as f:
                f.write(text_content)
                
            # また、全ページ結合用のテキストファイルにも追記モードで書き込むと便利かも
            full_text_path = os.path.join(save_dir, "full_text.txt")
            with open(full_text_path, "a", encoding="utf-8") as f:
                f.write(f"\n--- Page {page_num} ---\n")
                f.write(text_content)
                f.write("\n")
                
            print(f"OCR completed for page {page_num}. {len(lines)} lines extracted.")
            
        except Exception as e:
            print(f"OCR failed for page {page_num}: {e}")

    def capture_loop(self, title: str) -> Tuple[int, str]:
        # Override capture_loop to inject OCR
        save_dir = os.path.join(self.config.IMG_OUTPUT_DIR, title)
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
            
        # OCR初期化
        self.initialize_ocr()
        
        # 既存のfull_text.txtがあればリセット
        full_text_path = os.path.join(save_dir, "full_text.txt")
        if os.path.exists(full_text_path):
            os.remove(full_text_path)

        print(f"Saving images and text to: {save_dir}")
        
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
                    return page - 1, save_dir

            # 画像保存
            self._save_image(current_image, filename)
            
            # OCR実行
            self._perform_ocr_and_save(current_image, page, save_dir)
            
            print(f'Page: {page}, {current_image.shape}, {time.perf_counter() - start_time:.2f} sec')

            old_image = current_image
            page += 1
            self._next_page()
