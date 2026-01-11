import os
import sys
import argparse
import glob
import cv2
from tkinter import filedialog, Tk

# Add parent dir
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ocr.ocr_engine import get_ocr_engine

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

    # Find Images
    image_files = sorted(glob.glob(os.path.join(target_dir, "*.png")))
    print(f"Found {len(image_files)} images.")
    
    full_text_path = os.path.join(target_dir, "full_text.txt")
    if os.path.exists(full_text_path):
        os.remove(full_text_path)

    for img_path in image_files:
        basename = os.path.basename(img_path)
        print(f"Processing {basename}...")
        
        try:
            img = cv2.imread(img_path)
            if img is None:
                print("Failed to load image.")
                continue
                
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            results = engine.extract_text(img_rgb)
            
            lines = [item['text'] for item in results]
            text_content = "\n".join(lines)
            
            # Save individual txt
            txt_path = img_path.replace('.png', '.txt')
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text_content)
                
            # Append to full
            with open(full_text_path, "a", encoding="utf-8") as f:
                f.write(f"\n--- {basename} ---\n")
                f.write(text_content)
                f.write("\n")
                
            print(f"  Saved {len(lines)} lines.")
            
        except Exception as e:
            print(f"  Error: {e}")

    print("Done. Text files saved.")

if __name__ == "__main__":
    main()
