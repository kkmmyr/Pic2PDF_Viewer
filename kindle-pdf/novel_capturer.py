import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Tuple

import numpy as np

from capturer import AutoConfig, AutoKindleCapturer

# プロジェクトルートの .env を読み込む（存在しない場合・dotenv 未インストール時は無視）
try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
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
    return os.path.abspath(
        os.path.join(base_dir, "..", "backend", "data", "kindle_novel", "images")
    )


@dataclass
class NovelConfig(AutoConfig):
    """小説用設定 (白背景前提)"""

    # 白背景判定の閾値 (RGB各値がこれ以上なら白とみなす)
    WHITE_THRESHOLD: int = 240

    # 文字検出幅が安全領域に占める最小比率。
    # これ未満は章扉・挿絵等による過剰クロップとみなし、安全領域全体を使う。
    MIN_CROP_WIDTH_RATIO: float = 0.9

    # 検出した左右端の外側へ残す余白
    DETECTION_PADDING_PX: int = 10

    # 画像出力先（env KINDLE_NOVEL_IMAGES_DIR で上書き可。backend と同じ env を参照）
    IMG_OUTPUT_DIR: str = _resolve_images_dir()


class NovelKindleCapturer(AutoKindleCapturer):
    """小説用キャプチャクラス (白背景検出 + 画像保存)"""

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
        content_height = self.config.CROP_Y2 - self.config.CROP_Y1
        scan_y_list = np.linspace(
            self.config.CROP_Y1 + content_height * 0.05,
            self.config.CROP_Y2 - content_height * 0.05,
            num_points,
            dtype=int,
        )

        left_edges: list[int] = []
        right_edges: list[int] = []

        # 小さい画面でも左右の探索領域が消えないよう、無視幅は画面幅の1/4までに制限する。
        offset_x = min(max(0, self.config.SIDE_IGNORE_PX), w // 4)
        safe_left = offset_x
        safe_right = w - offset_x  # exclusive

        print(
            f"Scanning for X-boundaries at Y={scan_y_list}, Offset={offset_x} (White Threshold={self.config.WHITE_THRESHOLD})"
        )

        for y in scan_y_list:
            row = img[y]
            # 白画素判定: すべてのチャンネルが閾値以上
            is_white = np.all(row >= self.config.WHITE_THRESHOLD, axis=1)

            non_white = np.flatnonzero(~is_white[safe_left:safe_right])
            if non_white.size == 0:
                # 空白行を safe_left/safe_right として採用すると、ページ内容だけで
                # 検出幅が変動するため境界候補から除外する。
                continue

            left_edges.append(safe_left + int(non_white[0]))
            right_edges.append(safe_left + int(non_white[-1]) + 1)

        safe_width = safe_right - safe_left
        if left_edges:
            final_left = min(left_edges)
            final_right = max(right_edges)
            detected_width = final_right - final_left
        else:
            final_left = safe_left
            final_right = safe_right
            detected_width = 0

        min_width = int(safe_width * self.config.MIN_CROP_WIDTH_RATIO)
        if detected_width < min_width:
            print(
                "Detected content is narrower than the safe minimum; "
                f"using safe bounds ({safe_left}, {safe_right})."
            )
            final_left = safe_left
            final_right = safe_right

        # マージン適用 (文字ギリギリだと窮屈なので、少し広げる)
        # DETECTION_MARGIN は正の値だと内側(狭くなる)ので、負にして広げるか、定数を調整する
        # ここでは文字の周りに余白を持たせるため、少し外側へ
        padding = self.config.DETECTION_PADDING_PX
        self.config.CROP_X1 = max(0, final_left - padding)
        self.config.CROP_X2 = min(w, final_right + padding)

        print(f"Novel Scan results (Left): {left_edges} -> Selected: {final_left}")
        print(
            f"Novel Scan results (Right, exclusive): {right_edges} -> Selected: {final_right}"
        )
        print(
            f"Detected boundaries: Left={self.config.CROP_X1}, Right={self.config.CROP_X2}"
        )

        if self.config.CROP_X1 >= self.config.CROP_X2:
            print("Warning: Detected invalid boundaries. Using full width.")
            self.config.CROP_X1 = 0
            self.config.CROP_X2 = w

    # _perform_ocr_and_save removed

    def capture_loop(
        self,
        title: str,
        on_page: Callable[[int], None] | None = None,
    ) -> Tuple[int, str]:
        """OCRを実行せず、連番画像だけを保存するキャプチャループ。"""
        return super().capture_loop(title, on_page=on_page)
