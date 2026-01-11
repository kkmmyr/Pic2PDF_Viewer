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

# Ensure directories exist
def ensure_directories():
    os.makedirs(PDF_DIR, exist_ok=True)
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)
    os.makedirs(COMPLETE_DIR, exist_ok=True)
    
    os.makedirs(KINDLE_PDF_DIR, exist_ok=True)
    os.makedirs(KINDLE_THUMBNAIL_DIR, exist_ok=True)
    os.makedirs(KINDLE_IMAGES_DIR, exist_ok=True)

ensure_directories()
