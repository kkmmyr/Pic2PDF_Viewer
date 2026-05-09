import os

import fitz

from utils.logger import get_logger

logger = get_logger(__name__)


class PdfService:
    @staticmethod
    def reorder_pages(pdf_path: str, page_indices: list[int]) -> int:
        """
        PDF のページ順序を `page_indices` の指す順に並び替える。

        Args:
            pdf_path: 対象 PDF のファイルパス
            page_indices: `[0..N-1]` の完全なパーミュテーション。
                `page_indices[i]` は新しい位置 i に配置する元ページの 0 始まりインデックス。

        Returns:
            並び替え後の総ページ数（= 元のページ数）

        Raises:
            FileNotFoundError: PDF ファイルが存在しない場合
            ValueError: page_indices が `[0..N-1]` のパーミュテーションでない場合
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        doc = None
        temp_path = pdf_path + ".tmp"
        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)

            if sorted(page_indices) != list(range(total_pages)):
                raise ValueError(
                    f"page_indices must be a permutation of [0..{total_pages - 1}], got: {page_indices}"
                )

            doc.select(page_indices)
            doc.save(temp_path)
            doc.close()
            doc = None

            os.replace(temp_path, pdf_path)
            logger.info("Reordered %d pages in %s", total_pages, pdf_path)
            return total_pages

        finally:
            if doc:
                doc.close()
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    @staticmethod
    def delete_pages(pdf_path: str, page_indices: list[int]) -> int:
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
        temp_path = pdf_path + ".tmp"
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
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
