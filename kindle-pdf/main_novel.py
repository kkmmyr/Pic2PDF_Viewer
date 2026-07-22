from tkinter import messagebox
from novel_capturer import NovelKindleCapturer


def main():
    try:
        capturer = NovelKindleCapturer()
    except Exception as e:
        messagebox.showerror("初期化エラー", f"Capturerの初期化に失敗しました: {e}")
        return

    if not capturer.find_window():
        messagebox.showerror("エラー", "Kindleが見つかりません")
        return

    try:
        capturer.setup_window()
        title = (
            capturer.get_book_title()
        )  # Inherited from KindleCapturer (simple dialog)

        if not title:
            capturer.cleanup()
            return

        total_pages, _image_save_dir = capturer.capture_loop(title)

        # 終了処理 (フルスクリーン解除)
        capturer.cleanup()

        msg = (
            f"撮影が終了しました。\n合計 {total_pages} 画面を処理しました。"
            "\n\n続いて管理画面（/novel/manage）からOCR・DB構築を実行してください。"
        )

        messagebox.showinfo("完了", msg)

    except Exception as e:
        try:
            capturer.cleanup()
        except Exception:
            pass
        messagebox.showerror("エラー", f"予期せぬエラーが発生しました: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    import sys

    # Ensure stdout/stderr are visible if run from console
    sys.stdout.reconfigure(encoding="utf-8")
    main()
