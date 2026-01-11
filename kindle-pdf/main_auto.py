from tkinter import messagebox
from capturer import AutoKindleCapturer

def main():
    capturer = AutoKindleCapturer()

    if not capturer.find_window():
        messagebox.showerror("エラー", "Kindleが見つかりません")
        return

    try:
        capturer.setup_window()
        title = capturer.get_book_title()
        
        if not title:
            capturer.cleanup()
            return
        
        # タイトル決定後、再度アクティブ化してマウス退避などが安全か確認
        # setup_windowで退避しているので基本OKだが、念のため
        # capturer.setup_window() # 二重実行は避ける
        
        total_pages, image_save_dir = capturer.capture_loop(title)
        
        # 終了処理 (フルスクリーン解除)
        capturer.cleanup()
        
        pdf_path = capturer.create_pdf(title, image_save_dir)
        
        msg = f"スクリーンショットの撮影が終了しました。\n合計 {total_pages} ページを保存しました。"
        if pdf_path:
            msg += f"\n\nPDFを作成しました:\n{pdf_path}"
        
        messagebox.showinfo("完了", msg)

    except Exception as e:
        # エラー時も試みてみる
        try:
            capturer.cleanup()
        except:
            pass
        messagebox.showerror("エラー", f"予期せぬエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
