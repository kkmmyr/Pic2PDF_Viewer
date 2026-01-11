import os
import sys
import glob
import cv2
import numpy as np
from tkinter import filedialog, Tk, messagebox
from PIL import Image

# Add parent dir
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ocr.ocr_engine import get_ocr_engine
from searchable_pdf import SearchablePdfGenerator

def main():
    root = Tk()
    root.withdraw()

    print("対象の画像フォルダ（001.pngなどが保存されているフォルダ）を選択してください。")
    target_dir = filedialog.askdirectory(title="画像フォルダを選択")
    
    if not target_dir:
        print("フォルダが選択されませんでした。")
        return

    print(f"Selected dir: {target_dir}")
    
    # OCR Engine Init
    try:
        engine = get_ocr_engine('yomitoku')
        engine.initialize()
    except Exception as e:
        print(f"OCR Engine Init Failed: {e}")
        return

    # PDF Generator Init
    folder_name = os.path.basename(target_dir) or "output"
    pdf_path = os.path.join(target_dir, f"{folder_name}_searchable.pdf")
    pdf_gen = SearchablePdfGenerator(pdf_path, debug_mode=False)

    # Find Images
    # Supports png and webp
    image_files = sorted(glob.glob(os.path.join(target_dir, "*.png")) + glob.glob(os.path.join(target_dir, "*.webp")))
    print(f"Found {len(image_files)} images.")
    
    full_text_path = os.path.join(target_dir, "full_text.txt")
    if os.path.exists(full_text_path):
        os.remove(full_text_path)

    for img_path in image_files:
        basename = os.path.basename(img_path)
        print(f"Processing {basename}...")
        
        try:
            # Use PIL to load to avoid OpenCV unicode path issues
            with Image.open(img_path) as pil_img:
                pil_rgb = pil_img.convert('RGB')
                img_rgb = np.array(pil_rgb)

            results = engine.extract_text(img_rgb)
            
            lines = [item['text'] for item in results]
            text_content = "\n".join(lines)
            
            # Save individual txt
            txt_path = os.path.splitext(img_path)[0] + '.txt'
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text_content)
                
            # Append to full
            with open(full_text_path, "a", encoding="utf-8") as f:
                f.write(f"\n--- {basename} ---\n")
                f.write(text_content)
                f.write("\n")
                
            # Add to PDF
            pdf_gen.add_page(img_path, results)
            
            print(f"  Saved {len(lines)} lines.")
            
        except Exception as e:
            print(f"  Error processing {basename}: {e}")
            import traceback
            traceback.print_exc()

    # Save PDF
    try:
        pdf_gen.save()
        print(f"Searchable PDF saved: {pdf_path}")
        messagebox.showinfo("完了", f"処理が完了しました。\nPDF: {pdf_path}")
    except Exception as e:
        print(f"Failed to save PDF: {e}")
        messagebox.showerror("エラー", f"PDFの保存に失敗しました: {e}")

if __name__ == "__main__":
    main()
