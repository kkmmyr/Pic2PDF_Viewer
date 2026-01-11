from tkinter import messagebox
from capturer import KindleCapturer

def main():
    capturer = KindleCapturer()

    if not capturer.find_window():
        messagebox.showerror("エラー", "Kindleが見つかりません")
        return

    try:
        capturer.setup_window()
        title = capturer.get_book_title()
        
        if not title:
            return

        total_pages, image_save_dir = capturer.capture_loop(title)
        
        pdf_path = capturer.create_pdf(title, image_save_dir)
        
        msg = f"スクリーンショットの撮影が終了しました。\n合計 {total_pages} ページを保存しました。"
        if pdf_path:
            msg += f"\n\nPDFを作成しました:\n{pdf_path}"
        
        messagebox.showinfo("完了", msg)

    except Exception as e:
        messagebox.showerror("エラー", f"予期せぬエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
