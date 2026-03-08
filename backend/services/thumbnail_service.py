import os
import fitz

class ThumbnailService:
    @staticmethod
    def generate_thumbnail(pdf_path: str, thumbnail_path: str, scale: float = 0.5):
        """
        Generate a thumbnail image (JPG) for the first page of a PDF.
        """
        try:
            os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
            with fitz.open(pdf_path) as doc:
                if len(doc) > 0:
                    page = doc.load_page(0)
                    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
                    pix.save(thumbnail_path)
                    return True
            return False
        except Exception as e:
            print(f"Failed to generate thumbnail for {pdf_path}: {e}")
            return False
