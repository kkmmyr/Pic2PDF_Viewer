import os
import sys
import glob
import cv2
import numpy as np
from PIL import Image

# OCR module path setup (共通venvで実行する前提)
OCR_MODULE_PATH = r"D:\61.tool\common\ocr"
if OCR_MODULE_PATH not in sys.path:
    sys.path.insert(0, OCR_MODULE_PATH)

from ocr_engine import get_ocr_engine
from searchable_pdf import SearchablePdfGenerator

# Hardcoded Paths (relative to this script)
# backend/data/kindle_novel/images, pdfs
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# ../backend/data/kindle_novel
KINDLE_NOVEL_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..', 'backend', 'data', 'kindle_novel'))
IMAGES_ROOT = os.path.join(KINDLE_NOVEL_ROOT, 'images')
PDFS_ROOT = os.path.join(KINDLE_NOVEL_ROOT, 'pdfs')

def process_book_folder(book_path: str, engine):
    """
    Process a single book folder:
    1. Scan images
    2. OCR
    3. Generate PDF
    """
    folder_name = os.path.basename(book_path)
    print(f"Checking book: {folder_name}")
    
    # Define PDF output path
    pdf_path = os.path.join(PDFS_ROOT, f"{folder_name}.pdf")
    
    if os.path.exists(pdf_path):
        print(f"  Skipping: PDF already exists at {pdf_path}")
        return

    print(f"  Start processing for {folder_name}...")
    
    # Find Images
    image_files = sorted(glob.glob(os.path.join(book_path, "*.png")) + glob.glob(os.path.join(book_path, "*.webp")))
    if not image_files:
        print("  No images found.")
        return

    print(f"  Found {len(image_files)} images.")

    # PDF Generator
    pdf_gen = SearchablePdfGenerator(pdf_path, debug_mode=False)
    
    # Full Text Output (Optional, inside images folder for reference?)
    # or inside PDFs folder? Let's keep inside images folder for now (or skip it if not needed).
    # User said "OCRは一切しない" for novel_capturer, but here we do OCR.
    # We can save separate text files if useful, but main goal is PDF.
    
    for img_path in image_files:
        basename = os.path.basename(img_path)
        # print(f"    Processing {basename}...")
        
        try:
            with Image.open(img_path) as pil_img:
                pil_rgb = pil_img.convert('RGB')
                img_rgb = np.array(pil_rgb)

            results = engine.extract_text(img_rgb)
            
            # Save PDF page
            pdf_gen.add_page(img_path, results)
            
        except Exception as e:
            print(f"    Error processing {basename}: {e}")

    # Save PDF
    try:
        pdf_gen.save()
        print(f"  [SUCCESS] Created PDF: {pdf_path}")
    except Exception as e:
        print(f"  [FAILED] Could not save PDF: {e}")


def main():
    print(f"Search Target: {IMAGES_ROOT}")
    print(f"PDF Output: {PDFS_ROOT}")
    
    if not os.path.exists(IMAGES_ROOT):
        print("Images directory does not exist.")
        return

    if not os.path.exists(PDFS_ROOT):
        os.makedirs(PDFS_ROOT)

    # Initialize OCR Engine once
    try:
        print("Initializing OCR Engine...")
        engine = get_ocr_engine('yomitoku')
        engine.initialize()
    except Exception as e:
        print(f"OCR Init Failed: {e}")
        return

    # Scan all directories in IMAGES_ROOT
    # os.listdir + isdir check
    subdirs = [f for f in os.listdir(IMAGES_ROOT) if os.path.isdir(os.path.join(IMAGES_ROOT, f))]
    subdirs.sort()
    
    print(f"Found {len(subdirs)} book folders.")
    
    for subdir in subdirs:
        book_path = os.path.join(IMAGES_ROOT, subdir)
        process_book_folder(book_path, engine)
        
    print("All processing finished.")

if __name__ == "__main__":
    main()
