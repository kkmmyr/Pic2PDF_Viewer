import pyautogui as pag
import os
import os.path as osp
import datetime
import time
import re
from dataclasses import dataclass
from typing import Tuple, Optional, List
from ctypes import windll, create_unicode_buffer, pointer, c_bool, c_int, POINTER, WINFUNCTYPE
from ctypes.wintypes import RECT

import cv2
import numpy as np
from PIL import ImageGrab, Image
from tkinter import messagebox, simpledialog

@dataclass
class Config:
    """アプリケーション設定"""
    KINDLE_WINDOW_TITLE: str = 'Kindle for PC'
    PAGE_CHANGE_KEY: str = 'left'  # ページめくりキー
    WAIT_SEC: float = 0.15         # キー入力後の微小待機
    PAGE_TURN_WAIT: float = 0.5    # ページめくり完了待ち
    TIMEOUT_SEC: float = 5.0       # ページ変化待ちタイムアウト

    # キャプチャ領域 (ウィンドウ左上からの相対座標)
    CROP_X1: int = 111
    CROP_Y1: int = 113
    CROP_X2: int = 1314
    CROP_Y2: int = 1822

    # 出力先パス
    BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
    # IMG_OUTPUT_DIR: str = os.path.join(BASE_DIR, 'output', 'img')
    # PDF_OUTPUT_DIR: str = os.path.join(BASE_DIR, 'output', 'pdf')
    
    # Backend data integration
    IMG_OUTPUT_DIR: str = os.path.abspath(os.path.join(BASE_DIR, '..', 'backend', 'data', 'kindle', 'images'))
    PDF_OUTPUT_DIR: str = os.path.abspath(os.path.join(BASE_DIR, '..', 'backend', 'data', 'kindle', 'pdfs'))

    # タイトルクリーニング用
    TITLE_PREFIX: str = "Kindle for PC - "
    REMOVE_AUTHOR_STR: str = "工藤智康さんの"

class KindleCapturer:
    """Kindleの画面キャプチャとPDF化を行うクラス"""

    def __init__(self):
        self.config = Config()
        self.hwnd = None
        self.rect = None

    def find_window(self) -> Optional[int]:
        """Kindleウィンドウを検索してハンドルを返す"""
        EnumWindows = windll.user32.EnumWindows
        GetWindowText = windll.user32.GetWindowTextW
        GetWindowTextLength = windll.user32.GetWindowTextLengthW
        WNDENUMPROC = WINFUNCTYPE(c_bool, POINTER(c_int), POINTER(c_int))
        
        found_hwnd = None

        def EnumWindowsProc(hwnd, lParam):
            nonlocal found_hwnd
            length = GetWindowTextLength(hwnd)
            buff = create_unicode_buffer(length + 1)
            GetWindowText(hwnd, buff, length + 1)
            if self.config.KINDLE_WINDOW_TITLE in buff.value:
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
        if self.config.TITLE_PREFIX in window_text:
            default_title = window_text.replace(self.config.TITLE_PREFIX, "")
            default_title = default_title.replace(self.config.REMOVE_AUTHOR_STR, "")
            
            # 空白・改行の正規化
            default_title = re.sub(r'\s+', ' ', default_title).strip()
            
            # 禁止文字の置換
            invalid_chars = '<>:"/\\|?*'
            for char in invalid_chars:
                default_title = default_title.replace(char, '_')

        if not default_title:
            default_title = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

        title = simpledialog.askstring('タイトルを入力', 'タイトルを入力して下さい', initialvalue=default_title)
        return title if title else default_title

    def _capture_screen(self) -> np.ndarray:
        """現在の設定範囲でスクリーンショットを取得"""
        # 矩形情報の更新（ウィンドウ移動に対応するため毎回取得が望ましいが、今回は固定クロップなのでrect基準）
        # ただしsetup_windowで取得したrectを使用（ウィンドウが動かない前提）
        
        capture_left = self.rect.left + self.config.CROP_X1
        capture_top = self.rect.top + self.config.CROP_Y1
        capture_right = self.rect.left + self.config.CROP_X2
        capture_bottom = self.rect.top + self.config.CROP_Y2

        image = ImageGrab.grab(bbox=(capture_left, capture_top, capture_right, capture_bottom))
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

    def capture_loop(self, title: str) -> Tuple[int, str]:
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

            while True:
                time.sleep(self.config.WAIT_SEC)
                current_image = self._capture_screen()

                if old_image is None:
                    break
                
                # 画像比較 (完全一致でなければ変化ありとみなす)
                if not np.array_equal(old_image, current_image):
                    break

                if time.perf_counter() - start_time > self.config.TIMEOUT_SEC:
                    print("Timeout: Page did not change.")
                    return page - 1, save_dir

            self._save_image(current_image, filename)
            print(f'Page: {page}, {current_image.shape}, {time.perf_counter() - start_time:.2f} sec')

            old_image = current_image
            page += 1
            self._next_page()

    def create_pdf(self, title: str, image_dir: str) -> Optional[str]:
        """保存された画像をPDFに変換"""
        try:
            if not os.path.exists(self.config.PDF_OUTPUT_DIR):
                os.makedirs(self.config.PDF_OUTPUT_DIR)

            pdf_path = os.path.join(self.config.PDF_OUTPUT_DIR, f"{title}.pdf")
            image_files = sorted([f for f in os.listdir(image_dir) if f.endswith('.png')])

            if not image_files:
                print("No images found to convert.")
                return None

            print(f"Converting {len(image_files)} images to PDF...")
            
            images = []
            for img_file in image_files:
                img_path = os.path.join(image_dir, img_file)
                img = Image.open(img_path)
                if img.mode == 'RGBA':
                    img = img.convert('RGB')
                images.append(img)

            if images:
                images[0].save(pdf_path, "PDF", resolution=100.0, save_all=True, append_images=images[1:])
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
    
    # 黒帯検出の閾値 (0-255)
    # RGBの各値がこの値以下なら黒とみなす
    BLACK_THRESHOLD: int = 20
    
    # コンテンツ検出時のマージン (検出された境界からさらに内側/外側へ)
    DETECTION_MARGIN: int = 0

    # 左右のUI（矢印など）を無視するためのマージン
    SIDE_IGNORE_PX: int = 500

class AutoKindleCapturer(KindleCapturer):
    """フルスクリーン・動的クロップ版キャプチャクラス"""
    
    def __init__(self):
        super().__init__()
        self.config = AutoConfig() # 設定を上書き
        
    def setup_window(self):
        """ウィンドウをアクティブ化し、フルスクリーンモードに設定"""
        if not self.hwnd:
            raise RuntimeError("Window handle not found. Call find_window() first.")

        # まずアクティブ化
        windll.user32.SetForegroundWindow(self.hwnd)
        time.sleep(0.5)
        
        # フルスクリーン化 (F11)
        pag.press('f11')
        print("Entering fullscreen mode...")
        time.sleep(3.0) # アニメーション待機
        
        # フルスクリーンになったのでRectを画面全体で更新
        # ただし find_window で取得した hwnd の rect はフルスクリーンになっても更新されない場合があるため
        # 画面サイズ自体を取得して使用する
        screen_w, screen_h = pag.size()
        
        # 動的検出を実行
        print("Detecting content boundaries...")
        full_img = ImageGrab.grab() # 全画面キャプチャ
        img_np = np.array(full_img)
        
        self._detect_boundaries(img_np, screen_w, screen_h)
        
        # ウィンドウ矩形情報も更新しておく (マウス移動の基準などに使うため)
        # ただしフルスクリーンなので (0, 0, w, h)
        class RectShim:
            left = 0
            top = 0
            right = screen_w
            bottom = screen_h
        self.rect = RectShim()

        # マウスカーソルを右の黒帯部分へ退避
        # コンテンツ右端より右側へ
        safe_x = min(self.config.CROP_X2 + 50, screen_w - 10)
        safe_y = screen_h // 2
        pag.moveTo(safe_x, safe_y)
        print(f"Mouse moved to safe area: ({safe_x}, {safe_y})")

    def _detect_boundaries(self, img: np.ndarray, w: int, h: int):
        """
        全画面画像からコンテンツ領域を検出して config を更新する
        複数行をスキャンして、最も広い範囲を採用する (誤検出対策)
        """
        # 上下は固定値
        self.config.CROP_Y1 = self.config.FULLSCREEN_CROP_TOP
        self.config.CROP_Y2 = h - self.config.FULLSCREEN_CROP_BOTTOM_MARGIN
        
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
        print(f"Detected boundaries: Left={self.config.CROP_X1}, Right={self.config.CROP_X2}")
        
        # 異常値チェック
        if self.config.CROP_X1 >= self.config.CROP_X2:
            print("Warning: Detected invalid boundaries. Using full width.")
            self.config.CROP_X1 = 0
            self.config.CROP_X2 = w

    def cleanup(self):
        """終了処理: フルスクリーン解除"""
        if self.hwnd:
            windll.user32.SetForegroundWindow(self.hwnd)
            time.sleep(0.5)
            pag.press('f11')
            time.sleep(1.0)
            print("Exited fullscreen mode.")
