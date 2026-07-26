import pyautogui as pag
import os
import os.path as osp
import datetime
import time
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional, Tuple
from ctypes import (
    POINTER,
    WINFUNCTYPE,
    Structure,
    c_void_p,
    create_unicode_buffer,
    pointer,
    sizeof,
    windll,
)
from ctypes import wintypes
from ctypes.wintypes import RECT

import cv2
import numpy as np
from PIL import ImageGrab, Image
import tkinter as tk
from tkinter import messagebox, simpledialog

# プロジェクトルートの .env を読み込む（存在しない場合・dotenv 未インストール時は無視）
try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
except ImportError:
    pass


def _resolve_comic_dir(subdir: str) -> str:
    """漫画キャプチャの出力先を解決する。
    PIC2PDF_DATA_DIR が設定されていればその配下、なければ backend/data/comic/ を使う。"""
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
    PAGE_CHANGE_KEY: str = "left"  # ページめくりキー (デフォルト)
    WAIT_SEC: float = 0.15  # キー入力後の微小待機
    PAGE_TURN_WAIT: float = 0.5  # ページめくり完了待ち
    TIMEOUT_SEC: float = 5.0  # ページ変化待ちタイムアウト
    PAGE_STABLE_SEC: float = 0.75  # 同一画像が続けば描画完了とみなす時間
    PAGE_VISUAL_DIFF_THRESHOLD: float = 1.0  # UI微小変化を同一画面とみなす平均画素差
    PAGE_CHANGE_RETRY_COUNT: int = 1  # 画面無変化時のページ送り再試行回数
    EXPECTED_PAGES: Optional[int] = None  # 表紙等を含む期待撮影枚数

    # キャプチャ領域 (ウィンドウ左上からの相対座標)
    CROP_X1: int = 111
    CROP_Y1: int = 113
    CROP_X2: int = 1314
    CROP_Y2: int = 1822

    # 出力先パス（env PIC2PDF_DATA_DIR/comic/ または backend/data/comic/）
    BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
    IMG_OUTPUT_DIR: str = _resolve_comic_dir("images")
    PDF_OUTPUT_DIR: str = _resolve_comic_dir("pdfs")

    # タイトルクリーニング用 (正規表現で PC 後のバージョン番号に対応)
    # 旧: 'Kindle for PC - Title' / 新: 'Kindle - Title'（タイトルが出ない場合は空→ダイアログで手入力）
    TITLE_PATTERN: str = r"(?:Kindle for PC\d*|Kindle)\s*-\s*(.+)"


class BookInfoDialog(simpledialog.Dialog):
    def __init__(self, parent, title, initialvalue):
        self.initialvalue = initialvalue
        self.result_title = None
        self.result_direction = None
        self.result_expected_pages = None
        super().__init__(parent, title)

    def body(self, master):
        tk.Label(master, text="タイトル:").grid(
            row=0, column=0, sticky="w", padx=5, pady=5
        )
        self.e_title = tk.Entry(master, width=50)
        self.e_title.insert(0, self.initialvalue)
        self.e_title.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(master, text="ページめくり:").grid(
            row=1, column=0, sticky="w", padx=5, pady=5
        )

        self.var_direction = tk.StringVar(
            value="left"
        )  # Default: Left Key (Standard for Vertical)

        frame_dir = tk.Frame(master)
        frame_dir.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        # Note: In Kindle PC:
        # Vertical Text (Manga/Novel) -> Press Left Arrow to go Next.
        # Horizontal Text (Tech Book) -> Press Right Arrow to go Next.
        tk.Radiobutton(
            frame_dir,
            text="左キー (縦書き/右開き)",
            variable=self.var_direction,
            value="left",
        ).pack(side="left", padx=5)
        tk.Radiobutton(
            frame_dir,
            text="右キー (横書き/左開き)",
            variable=self.var_direction,
            value="right",
        ).pack(side="left", padx=5)

        tk.Label(master, text="撮影画面数（任意・通常は空欄）:").grid(
            row=2, column=0, sticky="w", padx=5, pady=5
        )
        self.e_expected_pages = tk.Entry(master, width=12)
        self.e_expected_pages.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        return self.e_title  # Focus

    def validate(self):
        raw_value = self.e_expected_pages.get().strip()
        if raw_value and (not raw_value.isdecimal() or int(raw_value) <= 0):
            messagebox.showwarning(
                "入力エラー",
                "撮影画面数には1以上の整数を入力するか、空欄にしてください。",
                parent=self,
            )
            return False
        return True

    def apply(self):
        self.result_title = self.e_title.get()
        self.result_direction = self.var_direction.get()
        raw_value = self.e_expected_pages.get().strip()
        self.result_expected_pages = int(raw_value) if raw_value else None


class KindleCapturer:
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
        EnumWindows = windll.user32.EnumWindows
        GetWindowText = windll.user32.GetWindowTextW
        GetWindowTextLength = windll.user32.GetWindowTextLengthW
        WNDENUMPROC = WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        found_hwnd = None

        def EnumWindowsProc(hwnd, lParam):
            nonlocal found_hwnd
            length = GetWindowTextLength(hwnd)
            buff = create_unicode_buffer(length + 1)
            GetWindowText(hwnd, buff, length + 1)
            if buff.value.startswith(self.config.KINDLE_WINDOW_TITLE):
                found_hwnd = hwnd
                return False
            return True

        EnumWindows(WNDENUMPROC(EnumWindowsProc), 0)
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

        # フォーカス確保のためにウィンドウ中央をクリック
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
        m = re.search(self.config.TITLE_PATTERN, window_text)
        if m:
            default_title = m.group(1)

            # 空白・改行の正規化
            default_title = re.sub(r"\s+", " ", default_title).strip()

            # 禁止文字の置換
            invalid_chars = '<>:"/\\|?*'
            for char in invalid_chars:
                default_title = default_title.replace(char, "_")

        if not default_title:
            default_title = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

        # Use Custom Dialog
        root = tk.Tk()
        root.withdraw()  # Hide main window

        # Ensure dialog is top most
        root.attributes("-topmost", True)

        d = BookInfoDialog(root, "書籍情報入力", default_title)

        if d.result_title:
            # Update config with selected direction
            self.config.PAGE_CHANGE_KEY = d.result_direction
            self.config.EXPECTED_PAGES = d.result_expected_pages
            print(f"Set page turn key to: {self.config.PAGE_CHANGE_KEY}")
            if self.config.EXPECTED_PAGES:
                print(f"Expected capture count: {self.config.EXPECTED_PAGES}")
            return d.result_title
        else:
            # Cancelled or closed
            return None

    def _capture_screen(self) -> np.ndarray:
        """現在の設定範囲でスクリーンショットを取得"""
        # 矩形情報の更新（ウィンドウ移動に対応するため毎回取得が望ましいが、今回は固定クロップなのでrect基準）
        # ただしsetup_windowで取得したrectを使用（ウィンドウが動かない前提）

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

    def _next_page(self):
        """ページめくり操作"""
        pag.keyDown(self.config.PAGE_CHANGE_KEY)
        time.sleep(0.1)
        pag.keyUp(self.config.PAGE_CHANGE_KEY)
        time.sleep(self.config.PAGE_TURN_WAIT)

    def _images_visually_equal(
        self,
        left: np.ndarray,
        right: np.ndarray,
    ) -> bool:
        if left.shape != right.shape:
            return False
        channel_means = cv2.mean(cv2.absdiff(left, right))[:3]
        mean_difference = sum(channel_means) / len(channel_means)
        return mean_difference < self.config.PAGE_VISUAL_DIFF_THRESHOLD

    def _wait_for_stable_page(
        self, previous_image: Optional[np.ndarray]
    ) -> Optional[np.ndarray]:
        """ページ変化後、画像が一定時間同一になるまで待つ。

        直前ページから一度も変化しなかった場合は ``None`` を返す。変化は
        観測できたもののタイムアウトまで安定しない場合は、ページスキップを
        避けるため例外にする。
        """
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

        # 撮影開始直前の再アクティブ化
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
                self._next_page()
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
                f"Page: {page}, {current_image.shape}, {time.perf_counter() - start_time:.2f} sec"
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

    def create_pdf(self, title: str, image_dir: str) -> Optional[str]:
        """保存された画像をPDFに変換"""
        try:
            if not os.path.exists(self.config.PDF_OUTPUT_DIR):
                os.makedirs(self.config.PDF_OUTPUT_DIR)

            pdf_path = os.path.join(self.config.PDF_OUTPUT_DIR, f"{title}.pdf")
            image_files = sorted(
                [f for f in os.listdir(image_dir) if f.endswith(".png")]
            )

            if not image_files:
                print("No images found to convert.")
                return None

            print(f"Converting {len(image_files)} images to PDF...")

            images = []
            for img_file in image_files:
                img_path = os.path.join(image_dir, img_file)
                img = Image.open(img_path)
                if img.mode == "RGBA":
                    img = img.convert("RGB")
                images.append(img)

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

        except Exception as e:
            print(f"PDF creation failed: {e}")
            messagebox.showerror("エラー", f"PDF作成中にエラーが発生しました: {e}")
            return None


class AutoConfig(Config):
    """メイン設定を継承し、自動検出用の設定を追加"""

    # 上下の固定クロップ値 (フルスクリーン時)
    FULLSCREEN_CROP_TOP: int = 0
    FULLSCREEN_CROP_BOTTOM_MARGIN: int = 0

    # 新 Kindle は F11 後の案内トーストを約5秒表示する。
    # 境界検出と初回キャプチャへ混入しないよう、実測値まで待機する。
    FULLSCREEN_SETTLE_SEC: float = 5.0

    # Microsoft Store 版 Kindle は F11 中のページ送りで本文が白くなるため、
    # 最大化ウィンドウを使い、アプリUIを固定値で撮影範囲から除外する。
    NEW_KINDLE_SETTLE_SEC: float = 2.0
    NEW_KINDLE_CROP_TOP: int = 56
    NEW_KINDLE_CROP_BOTTOM_MARGIN: int = 8
    NEW_KINDLE_SIDE_IGNORE_PX: int = 180

    # 黒帯検出の閾値 (0-255)
    # RGBの各値がこの値以下なら黒とみなす
    BLACK_THRESHOLD: int = 20

    # コンテンツ検出時のマージン (検出された境界からさらに内側/外側へ)
    DETECTION_MARGIN: int = 0

    # 左右のUI（矢印など）を無視するためのマージン
    SIDE_IGNORE_PX: int = 500

    # 自動agentの漫画はKindleを2ページ表示にして、見開き全体を保存する。
    CAPTURE_SPREAD: bool = False
    COMIC_WHITE_THRESHOLD: int = 245
    COMIC_MIN_PAGE_ASPECT_RATIO: float = 0.68
    COMIC_SPREAD_DETECTION_RATIO: float = 1.1
    COMIC_SPREAD_PADDING_PX: int = 16


class AutoKindleCapturer(KindleCapturer):
    """フルスクリーン・動的クロップ版キャプチャクラス"""

    def __init__(self):
        super().__init__()
        self.config = AutoConfig()  # 設定を上書き
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
            2,  # MONITOR_DEFAULTTONEAREST
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

        # まずアクティブ化
        windll.user32.SetForegroundWindow(self.hwnd)
        time.sleep(0.5)

        self._new_kindle_mode = self._get_window_title() == "Kindle"

        if self._new_kindle_mode:
            # F11状態で開始された場合は、ページ送り後の白画面を避けるため解除する。
            if self._is_fullscreen() and not windll.user32.IsZoomed(self.hwnd):
                self._restore_fullscreen_on_cleanup = True
                pag.press("f11")
                time.sleep(1.0)

            if windll.user32.IsZoomed(self.hwnd):
                print("Kindle is already maximized.")
            else:
                windll.user32.ShowWindow(self.hwnd, 3)  # SW_MAXIMIZE
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

        # primary monitor の pag.size() ではなく、対象ウィンドウの実座標を使う。
        # これにより Kindle を別モニターに配置した場合も同じ座標系で検出・撮影できる。
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

        # 動的検出を実行
        print("Detecting content boundaries...")
        full_img = ImageGrab.grab(
            bbox=(self.rect.left, self.rect.top, self.rect.right, self.rect.bottom),
            all_screens=True,
        )
        img_np = np.array(full_img)

        self._detect_boundaries(img_np, screen_w, screen_h)

        # UI操作や本文キャプチャへ混入しない位置へカーソルを退避する。
        if self._new_kindle_mode:
            safe_x = self.rect.left + screen_w // 2
            safe_y = self.rect.top + max(10, self.config.CROP_Y1 // 2)
        else:
            safe_x = self.rect.left + min(self.config.CROP_X2 + 50, screen_w - 10)
            safe_y = self.rect.top + screen_h // 2
        pag.moveTo(safe_x, safe_y)
        print(f"Mouse moved to safe area: ({safe_x}, {safe_y})")

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
        """
        全画面画像からコンテンツ領域を検出して config を更新する
        複数行をスキャンして、最も広い範囲を採用する (誤検出対策)
        """
        # 上下は固定値
        self.config.CROP_Y1 = self.config.FULLSCREEN_CROP_TOP
        self.config.CROP_Y2 = h - self.config.FULLSCREEN_CROP_BOTTOM_MARGIN

        if self.config.CAPTURE_SPREAD:
            self._detect_spread_boundaries(img, w)
            return

        # スキャンするY座標のリスト (上部1/4, 中央, 下部3/4)
        scan_y_list = [h // 4, h // 2, (h * 3) // 4]

        left_edges = []
        right_edges = []

        offset = self.config.SIDE_IGNORE_PX

        print(f"Scanning for boundaries at Y={scan_y_list}, Offset={offset}")

        for y in scan_y_list:
            row = img[y]
            is_black = np.all(row <= self.config.BLACK_THRESHOLD, axis=1)

            # 左端検出
            left = offset
            for x in range(offset, w):
                if not is_black[x]:
                    left = x
                    break
            left_edges.append(left)

            # 右端検出
            right = w - offset
            for x in range(w - 1 - offset, -1, -1):
                if not is_black[x]:
                    right = x
                    break
            right_edges.append(right)

        # 最も外側の値（コンテンツが一番広くなる値）を採用
        # 左端は最小値、右端は最大値
        final_left = min(left_edges)
        final_right = max(right_edges)

        # マージン適用
        self.config.CROP_X1 = final_left + self.config.DETECTION_MARGIN
        self.config.CROP_X2 = final_right - self.config.DETECTION_MARGIN

        print(f"Scan results (Left): {left_edges} -> Selected: {final_left}")
        print(f"Scan results (Right): {right_edges} -> Selected: {final_right}")
        print(
            f"Detected boundaries: Left={self.config.CROP_X1}, Right={self.config.CROP_X2}"
        )

        # 異常値チェック
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
            windll.user32.ShowWindow(self.hwnd, 9)  # SW_RESTORE
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
