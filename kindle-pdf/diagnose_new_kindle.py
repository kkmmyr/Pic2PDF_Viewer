"""
新 Kindle for Windows (Microsoft Store 版) 診断スクリプト
- ウィンドウタイトル一覧を列挙して Kindle を特定
- GetWindowDisplayAffinity でキャプチャ保護の有無を確認
- 試しにスクリーンショットを撮り、黒画面かどうかを判定
"""

import sys
from ctypes import byref, create_unicode_buffer
from ctypes.wintypes import BOOL, DWORD, HWND, LPARAM, RECT

import numpy as np
from PIL import ImageGrab

from kindle_platform import WINFUNCTYPE, windll


# ----- 定数 -----
WDA_NONE = 0x00000000
WDA_MONITOR = 0x00000001
WDA_EXCLUDEFROMCAPTURE = 0x00000011  # Windows 10 2004 以降

AFFINITY_NAMES = {
    WDA_NONE: "WDA_NONE (保護なし)",
    WDA_MONITOR: "WDA_MONITOR (モニタ表示のみ)",
    WDA_EXCLUDEFROMCAPTURE: "WDA_EXCLUDEFROMCAPTURE (キャプチャ除外！)",
}


def enum_windows() -> list[tuple[int, str]]:
    """全トップレベルウィンドウの (hwnd, title) を返す"""
    results = []
    WNDENUMPROC = WINFUNCTYPE(BOOL, HWND, LPARAM)

    def callback(hwnd, _):
        length = windll.user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = create_unicode_buffer(length + 1)
            windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            results.append((hwnd, buf.value))
        return True

    windll.user32.EnumWindows(WNDENUMPROC(callback), 0)
    return results


def get_display_affinity(hwnd: int) -> int:
    affinity = DWORD(0)
    windll.user32.GetWindowDisplayAffinity(hwnd, byref(affinity))
    return affinity.value


def capture_and_check_black(hwnd: int) -> tuple[bool, float]:
    """ウィンドウ全体をキャプチャして黒画面率を返す"""
    rect = RECT()
    windll.user32.GetWindowRect(hwnd, byref(rect))
    bbox = (rect.left, rect.top, rect.right, rect.bottom)
    img = ImageGrab.grab(bbox=bbox, all_screens=True)
    arr = np.array(img)
    black_pixels = np.sum(np.all(arr <= 10, axis=2))
    total_pixels = arr.shape[0] * arr.shape[1]
    black_ratio = black_pixels / total_pixels if total_pixels > 0 else 0.0
    return black_ratio > 0.95, black_ratio


def main():
    print("=" * 60)
    print("Kindle 新アプリ診断スクリプト")
    print("=" * 60)

    all_windows = enum_windows()

    # Kindle らしいウィンドウを抽出
    keywords = ["kindle", "amazon"]
    kindle_windows = [
        (hwnd, title)
        for hwnd, title in all_windows
        if any(k in title.lower() for k in keywords)
    ]

    if not kindle_windows:
        print("\n[警告] Kindle らしいウィンドウが見つかりません。")
        print("新 Kindle アプリを起動して本を開いた状態で再実行してください。")
        print("\n--- 参考: 全ウィンドウタイトル上位 30 件 ---")
        for hwnd, title in sorted(all_windows, key=lambda x: x[1])[:30]:
            print(f"  [{hwnd}] {title}")
        sys.exit(1)

    print(f"\n Kindle 関連ウィンドウ: {len(kindle_windows)} 件\n")

    for hwnd, title in kindle_windows:
        print(f"  タイトル : {title!r}")
        print(f"  HWND     : {hwnd}")
        if title == "Kindle":
            print("  種別     : 本文ウィンドウ（キャプチャ対象）")

        rect = RECT()
        windll.user32.GetWindowRect(hwnd, byref(rect))
        print(
            "  矩形     : "
            f"({rect.left}, {rect.top}, {rect.right}, {rect.bottom}) "
            f"{rect.right - rect.left}x{rect.bottom - rect.top}"
        )

        affinity = get_display_affinity(hwnd)
        affinity_label = AFFINITY_NAMES.get(affinity, f"不明 (0x{affinity:08X})")
        print(f"  Affinity : {affinity_label}")

        is_black, ratio = capture_and_check_black(hwnd)
        status = (
            "黒画面！(キャプチャ保護の可能性)"
            if is_black
            else "OK (画像取得できています)"
        )
        print(f"  キャプチャ: {status}  (黒画素率 {ratio:.1%})")
        print()

    # --- 総合判定 ---
    print("=" * 60)
    protected = any(
        get_display_affinity(hwnd) != WDA_NONE for hwnd, _ in kindle_windows
    )
    any_black = any(capture_and_check_black(hwnd)[0] for hwnd, _ in kindle_windows)
    capture_target_found = any(title == "Kindle" for _, title in kindle_windows)

    if protected or any_black:
        print("【結果】キャプチャ保護が検出されました。")
        print("  → TM-1 対応: 仮想ディスプレイ (IDD) 方式への切替が必要です。")
    elif not capture_target_found:
        print(
            "【結果】キャプチャ保護なし、ただし本文ウィンドウ 'Kindle' が見つかりません。"
        )
        print("  → 書籍を開いた状態で再実行してください。")
    else:
        print("【結果】本文ウィンドウを保護なしでキャプチャできます。")
        print("  → run_comic.bat / run_novel.bat の実機キャプチャを実行できます。")
    print("=" * 60)


if __name__ == "__main__":
    main()
