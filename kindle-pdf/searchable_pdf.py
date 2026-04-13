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

        縦書きテキストの配置方針:
          - 1文字ずつ縦に配置する（rotate方式は長い列が途中で切れるため廃止）
          - 各文字のy位置を上から順に計算して個別に TextObject を生成する
          - これによりPDFの検索・コピーで文字が正しく取得できる
        """
        for item in results:
            text = item['text']
            bbox = item['position']

            # Normalize bbox to [x1, y1, x2, y2]
            if isinstance(bbox, list) and isinstance(bbox[0], list):
                pts = np.array(bbox)
                x1 = float(np.min(pts[:, 0]))
                y1 = float(np.min(pts[:, 1]))
                x2 = float(np.max(pts[:, 0]))
                y2 = float(np.max(pts[:, 1]))
            else:
                x1, y1, x2, y2 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])

            rect_w = x2 - x1
            rect_h = y2 - y1

            if not text or rect_w < 1 or rect_h < 1:
                continue

            # 縦書き判定（高さが幅の2倍超）
            is_vertical = rect_h > rect_w * 2

            if is_vertical:
                self._draw_vertical_text(text, x1, y1, x2, y2, page_height)
            else:
                self._draw_horizontal_text(text, x1, y1, x2, y2, page_height)

    def _draw_vertical_text(self, text: str, x1: float, y1: float,
                            x2: float, y2: float, page_height: float):
        """
        縦書きテキストを1文字ずつ縦に配置する。

        各文字を bbox の上端から下端に向かって等間隔に並べる。
        ReportLab 座標系（原点=左下）に変換して配置。
        """
        rect_w = x2 - x1
        rect_h = y2 - y1
        n = len(text)
        if n == 0:
            return

        # フォントサイズ = 列幅（文字の横幅に合わせる）
        font_size = max(rect_w * 0.9, 6.0)

        # 1文字あたりの高さ（bbox全体をn文字で均等分割）
        char_step = rect_h / n

        # 文字の横中心 x（ReportLab座標）
        char_x = x1 + (rect_w - font_size) / 2

        for i, char in enumerate(text):
            # 画像座標: 文字の上端 y = y1 + i * char_step
            # 文字ベースラインはその1文字分下
            img_y_baseline = y1 + i * char_step + char_step * 0.8

            # ReportLab座標変換（y軸反転）
            pdf_y = page_height - img_y_baseline

            t = self.c.beginText()
            t.setFont(self.FONT_NAME, font_size)

            if self.debug_mode:
                self.c.setFillColor(Color(0, 0, 1, 0.3))
                t.setTextRenderMode(0)
            else:
                t.setTextRenderMode(3)

            t.setTextOrigin(char_x, pdf_y)
            t.textOut(char)
            self.c.drawText(t)

    def _draw_horizontal_text(self, text: str, x1: float, y1: float,
                              x2: float, y2: float, page_height: float):
        """横書きテキストをbbox内に配置する。"""
        rect_h = y2 - y1
        font_size = max(rect_h * 0.8, 6.0)

        # ReportLab座標変換（y軸反転、ベースラインは下端寄り）
        pdf_y = page_height - y2 + rect_h * 0.15

        t = self.c.beginText()
        t.setFont(self.FONT_NAME, font_size)

        if self.debug_mode:
            self.c.setFillColor(Color(0, 0, 1, 0.3))
            t.setTextRenderMode(0)
        else:
            t.setTextRenderMode(3)

        t.setTextOrigin(x1, pdf_y)
        t.textOut(text)
        self.c.drawText(t)

    def save(self):
        self.c.save()
        print(f"Saved PDF to {self.output_path}")
