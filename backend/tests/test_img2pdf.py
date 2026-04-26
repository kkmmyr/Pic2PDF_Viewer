import img2pdf
from PIL import Image
import io
import os

def test():
    print("Testing scan_and_generate with a real ZIP...")
    from services.pdf_generator import scan_and_generate
    from config import PDF_DIR, THUMBNAIL_DIR, IMAGES_DIR, COMPLETE_DIR
    
    source_dir = r"D:\61.tool\Pic2PDF_Viewer\backend\input"
    # Create dummy dirs for testing
    test_pdf_dir = r"D:\61.tool\Pic2PDF_Viewer\backend\data\test_pdfs"
    os.makedirs(test_pdf_dir, exist_ok=True)
    
    try:
        # We only want to test one file, so we'll mock the generator or just let it run on the directory
        # Actually, let's just call the generator on the input dir but use a different output dir to avoid mess
        generated = scan_and_generate(source_dir, test_pdf_dir, THUMBNAIL_DIR, IMAGES_DIR, COMPLETE_DIR)
        print("Success! Generated files:", generated)
    except Exception as e:
        print("Failed:", e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test()
