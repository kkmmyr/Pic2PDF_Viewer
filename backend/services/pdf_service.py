import os
import fitz
from typing import List, Optional

class PdfService:
    @staticmethod
    def delete_pages(pdf_path: str, page_indices: List[int]) -> int:
        """
        Delete specified pages from a PDF file.
        Returns the new total page count.
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        doc = None
        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            
            # Sort indices in reverse to avoid index shifting problems
            indices = sorted(list(set(page_indices)), reverse=True)
            for idx in indices:
                if idx < 0 or idx >= total_pages:
                    raise ValueError(f"Invalid page index: {idx}")

            for idx in indices:
                doc.delete_page(idx)
            
            temp_path = pdf_path + ".tmp"
            doc.save(temp_path)
            doc.close()
            doc = None
            
            os.replace(temp_path, pdf_path)
            
            # Re-open to get new page count
            with fitz.open(pdf_path) as doc_new:
                return len(doc_new)

        finally:
            if doc:
                doc.close()

    @staticmethod
    def get_page_count(pdf_path: str) -> int:
        if not os.path.exists(pdf_path):
            return 0
        with fitz.open(pdf_path) as doc:
            return len(doc)
