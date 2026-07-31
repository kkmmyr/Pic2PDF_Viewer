import datetime
import os
import re
import time
import tkinter as tk
from ctypes import WINFUNCTYPE, create_unicode_buffer, pointer, windll
from ctypes import wintypes
from ctypes.wintypes import RECT
from dataclasses import dataclass
from tkinter import messagebox
from typing import Optional

import pyautogui as pag
from PIL import Image

from capture_loop import CaptureLoopMixin
from capture_ui import BookInfoDialog

try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
except ImportError:
    pass


def _resolve_comic_dir(subdir: str) -> str:
    """漫画キャプチャの出力先を解決する。"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.environ.get("PIC2PDF_DATA_DIR")
    if data_dir:
        return os.path.join(data_dir, "comic", subdir)
    return os.path.abspath(
        os.path.join(base_dir, "..", "backend", "data", "comic", subdir)
    )


@dataclass
class Config:
    """アプリケーション設定"""

    KINDLE_WINDOW_TITLE: str = "Kindle"
    PAGE_CHANGE_KEY: str = "left"
    WAIT_SEC: float = 0.15
    PAGE_TURN_WAIT: float = 0.5
    TIMEOUT_SEC: float = 5.0
    PAGE_STABLE_SEC: float = 0.75
    PAGE_VISUAL_DIFF_THRESHOLD: float = 1.0
    PAGE_VISUAL_PIXEL_THRESHOLD: int = 20
    PAGE_VISUAL_CHANGED_RATIO_THRESHOLD: float = 0.001
    PAGE_CHANGE_RETRY_COUNT: int = 1
    EXPECTED_PAGES: Optional[int] = None

    CROP_X1: int = 111
    CROP_Y1: int = 113
    CROP_X2: int = 1314
    CROP_Y2: int = 1822

    BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
    IMG_OUTPUT_DIR: str = _resolve_comic_dir("images")
    PDF_OUTPUT_DIR: str = _resolve_comic_dir("pdfs")
    TITLE_PATTERN: str = r"(?:Kindle for PC\d*|Kindle)\s*-\s*(.+)"


class KindleCapturer(CaptureLoopMixin):
    """Kindleの画面キャプチャとPDF化を行うクラス"""

    def __init__(self):
        self.config = Config()
        self.hwnd = None
        self.rect = None
        self._entered_fullscreen = False
        self._restore_fullscreen_on_cleanup = False
        self._maximized_window = False
        self._new_kindle_mode = False

    def find_window(self) -> Optional[int]:
        """Kindleウィンドウを検索してハンドルを返す"""
        enum_windows = windll.user32.EnumWindows
        get_window_text = windll.user32.GetWindowTextW
        get_window_text_length = windll.user32.GetWindowTextLengthW
        enum_callback = WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        found_hwnd = None

        def enum_windows_proc(hwnd, _l_param):
            nonlocal found_hwnd
            length = get_window_text_length(hwnd)
            buff = create_unicode_buffer(length + 1)
            get_window_text(hwnd, buff, length + 1)
            if buff.value.startswith(self.config.KINDLE_WINDOW_TITLE):
                found_hwnd = hwnd
                return False
            return True

        enum_windows(enum_callback(enum_windows_proc), 0)
        self.hwnd = found_hwnd
        return found_hwnd

    def _get_window_rect(self) -> RECT:
        """ウィンドウの矩形領域を取得"""
        rect = RECT()
        windll.user32.GetWindowRect(self.hwnd, pointer(rect))
        return rect

    def _get_window_title(self) -> str:
        """現在の対象ウィンドウタイトルを返す。"""
        length = windll.user32.GetWindowTextLengthW(self.hwnd)
        buff = create_unicode_buffer(length + 1)
        windll.user32.GetWindowTextW(self.hwnd, buff, length + 1)
        return buff.value

    def setup_window(self):
        """ウィンドウをアクティブにしてフォーカスを設定"""
        if not self.hwnd:
            raise RuntimeError("Window handle not found. Call find_window() first.")

        windll.user32.SetForegroundWindow(self.hwnd)
        self.rect = self._get_window_rect()

        center_x = self.rect.left + (self.rect.right - self.rect.left) // 2
        center_y = self.rect.top + (self.rect.bottom - self.rect.top) // 2
        pag.moveTo(center_x, center_y)
        pag.click()
        time.sleep(1.0)

    def get_book_title(self) -> str:
        """ウィンドウタイトルから書籍名を取得してサニタイズ"""
        length = windll.user32.GetWindowTextLengthW(self.hwnd)
        buff = create_unicode_buffer(length + 1)
        windll.user32.GetWindowTextW(self.hwnd, buff, length + 1)
        window_text = buff.value

        default_title = ""
        match = re.search(self.config.TITLE_PATTERN, window_text)
        if match:
            default_title = re.sub(r"\s+", " ", match.group(1)).strip()
            invalid_chars = '<>:"/\\|?*'
            for char in invalid_chars:
                default_title = default_title.replace(char, "_")

        if not default_title:
            default_title = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        dialog = BookInfoDialog(root, "書籍情報入力", default_title)

        if dialog.result_title:
            self.config.PAGE_CHANGE_KEY = dialog.result_direction
            self.config.EXPECTED_PAGES = dialog.result_expected_pages
            print(f"Set page turn key to: {self.config.PAGE_CHANGE_KEY}")
            if self.config.EXPECTED_PAGES:
                print(f"Expected capture count: {self.config.EXPECTED_PAGES}")
            return dialog.result_title
        return None

    def create_pdf(self, title: str, image_dir: str) -> Optional[str]:
        """保存された画像をPDFに変換"""
        try:
            if not os.path.exists(self.config.PDF_OUTPUT_DIR):
                os.makedirs(self.config.PDF_OUTPUT_DIR)

            pdf_path = os.path.join(self.config.PDF_OUTPUT_DIR, f"{title}.pdf")
            image_files = sorted(
                [name for name in os.listdir(image_dir) if name.endswith(".png")]
            )

            if not image_files:
                print("No images found to convert.")
                return None

            print(f"Converting {len(image_files)} images to PDF...")

            images = []
            for image_file in image_files:
                image_path = os.path.join(image_dir, image_file)
                image = Image.open(image_path)
                if image.mode == "RGBA":
                    image = image.convert("RGB")
                images.append(image)

            if images:
                images[0].save(
                    pdf_path,
                    "PDF",
                    resolution=100.0,
                    save_all=True,
                    append_images=images[1:],
                )
                print(f"PDF saved to: {pdf_path}")
                return pdf_path
        except Exception as exc:
            print(f"PDF creation failed: {exc}")
            messagebox.showerror("エラー", f"PDF作成中にエラーが発生しました: {exc}")
        return None
