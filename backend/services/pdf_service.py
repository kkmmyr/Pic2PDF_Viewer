import os
import fitz
from typing import List
from utils.logger import get_logger

logger = get_logger(__name__)


class PdfService:
    @staticmethod
    def delete_pages(pdf_path: str, page_indices: List[int]) -> int:
        """
        PDF から指定したページを削除する。

        Args:
            pdf_path: 対象 PDF のファイルパス
            page_indices: 削除するページのインデックスリスト（0 始まり）

        Returns:
            削除後の総ページ数

        Raises:
            FileNotFoundError: PDF ファイルが存在しない場合
            ValueError: ページインデックスが範囲外の場合
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        doc = None
        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)

            # 重複排除 & 降順ソートでインデックスずれを防ぐ
            indices = sorted(set(page_indices), reverse=True)
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
            logger.info("Deleted %d pages from %s", len(indices), pdf_path)

            with fitz.open(pdf_path) as doc_new:
                return len(doc_new)

        finally:
            if doc:
                doc.close()

    @staticmethod
    def get_page_count(pdf_path: str) -> int:
        """PDF のページ数を返す。ファイルが存在しない場合は 0 を返す。"""
        if not os.path.exists(pdf_path):
            return 0
        with fitz.open(pdf_path) as doc:
            return len(doc)
