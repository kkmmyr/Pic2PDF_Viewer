import os

# Base Data Directory
# Assuming this file is in backend/config.py
BASE_DIR = os.path.dirname(os.path.dirname(__file__)) # Pointing to backend root
# But wait, config.py is inside backend/.
# so os.path.dirname(__file__) is backend.

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
MAIN_DATA_DIR = os.path.join(DATA_DIR, "main")

# Main Directories
PDF_DIR = os.path.join(MAIN_DATA_DIR, "pdfs")
PDF_COMPRESSED_DIR = os.path.join(MAIN_DATA_DIR, "pdfs_compressed")
THUMBNAIL_DIR = os.path.join(MAIN_DATA_DIR, "thumbnails")
IMAGES_DIR = os.path.join(MAIN_DATA_DIR, "images")
COMPLETE_DIR = os.path.join(MAIN_DATA_DIR, "complete")

# Kindle Directories
KINDLE_DIR = os.path.join(DATA_DIR, "kindle")
KINDLE_PDF_DIR = os.path.join(KINDLE_DIR, "pdfs")
KINDLE_THUMBNAIL_DIR = os.path.join(KINDLE_DIR, "thumbnails")
KINDLE_IMAGES_DIR = os.path.join(KINDLE_DIR, "images")

# Kindle Novel Directories
KINDLE_NOVEL_DIR = os.path.join(DATA_DIR, "kindle_novel")
KINDLE_NOVEL_PDF_DIR = os.path.join(KINDLE_NOVEL_DIR, "pdfs")
KINDLE_NOVEL_THUMBNAIL_DIR = os.path.join(KINDLE_NOVEL_DIR, "thumbnails")
KINDLE_NOVEL_IMAGES_DIR = os.path.join(KINDLE_NOVEL_DIR, "images")

# Ensure directories exist
def ensure_directories():
    os.makedirs(PDF_DIR, exist_ok=True)
    os.makedirs(PDF_COMPRESSED_DIR, exist_ok=True)
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)
    os.makedirs(COMPLETE_DIR, exist_ok=True)
    
    os.makedirs(KINDLE_PDF_DIR, exist_ok=True)
    os.makedirs(KINDLE_THUMBNAIL_DIR, exist_ok=True)
    os.makedirs(KINDLE_IMAGES_DIR, exist_ok=True)

    os.makedirs(KINDLE_NOVEL_PDF_DIR, exist_ok=True)
    os.makedirs(KINDLE_NOVEL_THUMBNAIL_DIR, exist_ok=True)
    os.makedirs(KINDLE_NOVEL_IMAGES_DIR, exist_ok=True)

    os.makedirs(KINDLE_NOVEL_IMAGES_DIR, exist_ok=True)

ensure_directories()

# OCR Configuration
import sys
# Default paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # f:\61.tool\Pic2PDF_Viewer

# OCR起動スクリプト (共通venv方式)
# start_batch_ocr.bat がPYTHONPATHと正しいPython環境を設定する
BATCH_OCR_LAUNCHER = os.path.join(PROJECT_ROOT, "kindle-pdf", "start_batch_ocr.bat")


def get_dirs_by_source(source: str) -> dict:
    """
    source文字列に応じてPDF/サムネイル/画像のディレクトリを返す共通ヘルパー。
    source: 'generated' | 'kindle' | 'novel'
    """
    if source == "kindle":
        return {
            "pdf": KINDLE_PDF_DIR,
            "thumb": KINDLE_THUMBNAIL_DIR,
            "img": KINDLE_IMAGES_DIR,
            "thumb_url_prefix": "/kindle/thumbnails",
        }
    elif source == "novel":
        return {
            "pdf": KINDLE_NOVEL_PDF_DIR,
            "thumb": KINDLE_NOVEL_THUMBNAIL_DIR,
            "img": KINDLE_NOVEL_IMAGES_DIR,
            "thumb_url_prefix": "/kindle_novel/thumbnails",
        }
    else:  # generated (default)
        return {
            "pdf": PDF_DIR,
            "thumb": THUMBNAIL_DIR,
            "img": IMAGES_DIR,
            "thumb_url_prefix": "/thumbnails",
        }
