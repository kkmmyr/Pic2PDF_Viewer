import sys
import os
import io
import cv2
import numpy as np
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import black, white, Color

# Add parent directory to path to import ocr module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ocr.ocr_engine import get_ocr_engine

# Target Directory
TARGET_TITLE = "おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)"
IMAGES_DIR = os.path.join(os.path.dirname(__file__), '..', 'backend', 'data', 'kindle', 'images', TARGET_TITLE)
OUTPUT_PDF = "searchable_test.pdf"

# Font Registration
FONT_PATH = "C:\\Windows\\Fonts\\msmincho.ttc"
FONT_NAME = "Japanese"

def register_font():
    try:
        pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))
        print(f"Registered font: {FONT_NAME}")
    except Exception as e:
        print(f"Failed to register font {FONT_PATH}: {e}")
        # Build fallback logic if needed, but Windows should have this.
        sys.exit(1)

def main():
    if not os.path.exists(IMAGES_DIR):
        print(f"Directory not found: {IMAGES_DIR}")
        return

    # Sort images
    files = [f for f in os.listdir(IMAGES_DIR) if f.lower().endswith('.png') or f.lower().endswith('.webp')]
    files.sort()
    
    # Process only first 3 pages for testing
    files = files[:3]
    print(f"Processing {len(files)} images...")

    register_font()

    # Initialize OCR
    ocr_engine = get_ocr_engine('yomitoku')
    ocr_engine.initialize(use_gpu=True)

    # Create PDF Canvas
    # We will set page size dynamically per image
    c = canvas.Canvas(OUTPUT_PDF)

    for i, filename in enumerate(files):
        print(f"Processing Page {i+1}: {filename}")
        img_path = os.path.join(IMAGES_DIR, filename)
        
        # Open Image to get size
        pil_img = Image.open(img_path)
        w, h = pil_img.size
        
        # Start Page
        c.setPageSize((w, h))

        # Draw Image
        # reportlab draws from bottom-left. (0,0) is bottom-left.
        # But images are usually top-left.
        # c.drawImage(path, x, y, width, height)
        c.drawImage(img_path, 0, 0, width=w, height=h)

        # Run OCR
        # Use PIL to load to avoid OpenCV unicode path issues
        pil_rgb = pil_img.convert('RGB')
        img_rgb = np.array(pil_rgb)
        
        # ocr_engine.extract_text expects RGB numpy array
        results = ocr_engine.extract_text(img_rgb)
        
        # Draw visible text for debugging (semi-transparent blue)
        # c.setTextRenderMode(3) # Caused AttributeError
        c.setFillColor(Color(0, 0, 1, 0.3)) # Blue, 0.3 alpha 
        
        for item in results:
            text = item['text']
            # Position: dict or list? extract_text normalize logic says:
            # Paragraphs: p.box (x1, y1, x2, y2)
            # Words: points [[x1,y1],...]
            # The current extract_text implementation normalizes to:
            # Paragraphs: 'position': p.box [x1, y1, x2, y2]
            # Words: 'position': [[x1, y1], [x2, y1], [x2, y2], [x1, y2]] (list of points)
            
            bbox = item['position']
            confidence = item['confidence']
            
            if isinstance(bbox, list) and isinstance(bbox[0], list):
                # Points format (Polygon) -> Convert to Rect
                pts = np.array(bbox)
                x1 = np.min(pts[:, 0])
                y1 = np.min(pts[:, 1])
                x2 = np.max(pts[:, 0])
                y2 = np.max(pts[:, 1])
            else:
                # Box format [x1, y1, x2, y2]
                x1, y1, x2, y2 = bbox
            
            # Coordinate system: ReportLab is Bottom-Up, Image/OCR is Top-Down
            # OCR Y is distance from Top.
            # ReportLab Y = h - OCR_Y.
            
            rect_w = x2 - x1
            rect_h = y2 - y1
            
            # Font Size estimation
            # For vertical text, use width? For horizontal, height?
            # Ideally we want the text to fill the box on PDF so selection highlights correct area.
            
            # Simple approach: Check direction (not in normalized dict currently, need to guess)
            is_vertical = rect_h > rect_w * 2 # Crude heuristic
            
            font_size = rect_w if is_vertical else rect_h
            if font_size < 1: font_size = 10
            
            c.setFont(FONT_NAME, font_size)
            
            # Determine drawing position (bottom-left of text for horizontal)
            # For vertical, reportlab doesn't do vertical text natively with simple drawString.
            # We will use horizontal text but rotate it? Or just place it there.
            # If we place horizontal text in vertical box, selection might be weird.
            # For prototype, let's just place text at (x1, inverted_y2).
            # inverted_y2 is the bottom of the rect in PDF coords.
            
            pdf_x = x1
            pdf_y = h - y2 # PDF Y starts from bottom. y2 is larger (lower) val in OCR.
            
            if is_vertical:
                # Rotation for vertical text
                c.saveState()
                c.translate(pdf_x + rect_w/2, h - y1) # Start near top-center of box
                c.rotate(-90) # Rotate 90 deg clockwise? Text runs down.
                # PDF 0 deg is right. -90 is down.
                c.drawString(0, 0, text)
                c.restoreState()
            else:
                c.drawString(pdf_x, pdf_y, text)

        c.showPage()
    
    c.save()
    print(f"Saved PDF to {OUTPUT_PDF}")

if __name__ == "__main__":
    main()
