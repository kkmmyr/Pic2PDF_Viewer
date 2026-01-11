import os
import sys
import numpy as np
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import Color

class SearchablePdfGenerator:
    """
    Generates a PDF with searchable text overlay (invisible text) from images and OCR results.
    """
    FONT_PATH = "C:\\Windows\\Fonts\\msmincho.ttc"
    FONT_NAME = "Japanese"

    def __init__(self, output_path: str, debug_mode: bool = False):
        self.output_path = output_path
        self.debug_mode = debug_mode
        self.c = canvas.Canvas(output_path)
        self._register_font()

    def _register_font(self):
        try:
            # Check if already registered
            try:
                pdfmetrics.getFont(self.FONT_NAME)
                return
            except:
                pass
                
            if os.path.exists(self.FONT_PATH):
                pdfmetrics.registerFont(TTFont(self.FONT_NAME, self.FONT_PATH))
                print(f"Registered font: {self.FONT_NAME}")
            else:
                print(f"Warning: Font not found at {self.FONT_PATH}. Text might not render correctly.")
        except Exception as e:
            print(f"Failed to register font: {e}")

    def add_page(self, image_path: str, ocr_results: list):
        """
        Adds a page to the PDF.
        :param image_path: Path to the underlying image.
        :param ocr_results: List of dicts [{'text': str, 'position': list, ...}] from OCR engine.
        """
        try:
            # Open Image to get size
            with Image.open(image_path) as pil_img:
                w, h = pil_img.size

            # Set Page Size
            self.c.setPageSize((w, h))

            # Draw Image (scaling to fit exactly)
            self.c.drawImage(image_path, 0, 0, width=w, height=h)

            # Draw Text
            self._draw_text_layer(ocr_results, h)

            self.c.showPage()
            print(f"Added page from {os.path.basename(image_path)}")

        except Exception as e:
            print(f"Failed to add page for {image_path}: {e}")

    def _draw_text_layer(self, results, page_height):
        """
        Draws invisible text over the image based on OCR coordinates.
        Using TextObject to ensure setTextRenderMode works reliably.
        """
        for item in results:
            text = item['text']
            bbox = item['position']
            
            # Normalize bbox to [x1, y1, x2, y2]
            if isinstance(bbox, list) and isinstance(bbox[0], list):
                # Points format (Polygon) -> Convert to Rect
                pts = np.array(bbox)
                x1 = np.min(pts[:, 0])
                y1 = np.min(pts[:, 1])
                x2 = np.max(pts[:, 0])
                y2 = np.max(pts[:, 1])
            else:
                x1, y1, x2, y2 = bbox
            
            rect_w = x2 - x1
            rect_h = y2 - y1
            
            # Heuristic for vertical text detection
            is_vertical = rect_h > rect_w * 2
            
            # Determine font size to approximately fill the box
            font_size = rect_w if is_vertical else rect_h
            if font_size < 1: font_size = 10
            
            # Create TextObject
            # Note: We create a new TextObject for each item to handle positioning/rotation individually
            t = self.c.beginText()
            t.setFont(self.FONT_NAME, font_size)
            
            if self.debug_mode:
                # Visible semi-transparent blue
                self.c.setFillColor(Color(0, 0, 1, 0.3))
                t.setTextRenderMode(0) # Fill text
            else:
                # Invisible
                t.setTextRenderMode(3) 

            # ReportLab coords (0,0 is bottom-left)
            pdf_x = x1
            pdf_y = page_height - y2 
            
            if is_vertical:
                self.c.saveState()
                # Vertical text handling with rotation
                pivot_x = pdf_x + rect_w / 2
                pivot_y = page_height - y1 # Top of the box
                
                self.c.translate(pivot_x, pivot_y) 
                self.c.rotate(-90) 
                
                # Draw text object at (0,0) relative to rotated canvas
                t.setTextOrigin(0, 0)
                t.textOut(text)
                self.c.drawText(t)
                
                self.c.restoreState()
            else:
                # Horizontal text
                t.setTextOrigin(pdf_x, pdf_y)
                t.textOut(text)
                self.c.drawText(t)

    def save(self):
        self.c.save()
        print(f"Saved PDF to {self.output_path}")
