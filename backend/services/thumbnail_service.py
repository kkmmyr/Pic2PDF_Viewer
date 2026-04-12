import os
import fitz
from utils.logger import get_logger

logger = get_logger(__name__)


class ThumbnailService:
    @staticmethod
    def generate_thumbnail(pdf_path: str, thumbnail_path: str, scale: float = 0.5) -> bool:
        """
        PDF の先頭ページからサムネイル (JPG) を生成する。

        Args:
            pdf_path: 対象 PDF のファイルパス
            thumbnail_path: 出力するサムネイルのパス
            scale: レンダリングスケール（デフォルト 0.5 = 50%）

        Returns:
            生成に成功した場合 True、それ以外 False
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
            logger.error("Failed to generate thumbnail for %s: %s", pdf_path, e)
            return False
