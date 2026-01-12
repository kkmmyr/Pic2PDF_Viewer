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

# Check for venv-gpu
GPU_VENV_PYTHON = os.path.join(PROJECT_ROOT, "venv-gpu", "Scripts", "python.exe")
if os.path.exists(GPU_VENV_PYTHON):
    OCR_PYTHON_PATH = GPU_VENV_PYTHON
else:
    # Fallback to current python
    OCR_PYTHON_PATH = sys.executable

BATCH_OCR_SCRIPT = os.path.join(PROJECT_ROOT, "kindle-pdf", "batch_ocr.py")
