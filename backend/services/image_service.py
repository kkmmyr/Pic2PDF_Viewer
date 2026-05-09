"""
image-only モード（generated ソース）の書籍ページ列を操作するサービス。

`PdfService` の image-only 版に相当する。書籍は `images/{path}/{book_name}/` 配下の
WebP ファイル列として表現され、natsort 順がページ順になる。
"""
import os

from natsort import natsorted

from utils.logger import get_logger

logger = get_logger(__name__)


def list_book_images(img_dir: str, book_name: str, path: str = "") -> list[str]:
    """`images/{path}/{book_name}/` 配下の WebP を natsort 順で絶対パスのリストとして返す。

    ディレクトリ不在時は空リスト。
    """
    target = os.path.join(img_dir, path, book_name) if path else os.path.join(img_dir, book_name)
    if not os.path.isdir(target):
        return []
    return [
        os.path.join(target, f)
        for f in natsorted(os.listdir(target))
        if f.lower().endswith('.webp')
    ]


def delete_book_image_pages(book_dir: str, page_indices: list[int]) -> int:
    """`book_dir` 配下の WebP を natsort 順に並べて、`page_indices` 番目を削除する。

    Args:
        book_dir: 書籍画像ディレクトリの絶対パス（`images/{path}/{book_name}/`）
        page_indices: 削除するページの 0 始まりインデックスリスト

    Returns:
        削除後の総ページ数

    Raises:
        FileNotFoundError: ディレクトリが存在しない場合
        ValueError: ページインデックスが範囲外の場合
    """
    if not os.path.isdir(book_dir):
        raise FileNotFoundError(f"Book images directory not found: {book_dir}")

    webps = [
        os.path.join(book_dir, f)
        for f in natsorted(os.listdir(book_dir))
        if f.lower().endswith('.webp')
    ]
    total_pages = len(webps)

    indices = sorted(set(page_indices), reverse=True)
    for idx in indices:
        if idx < 0 or idx >= total_pages:
            raise ValueError(f"Invalid page index: {idx}")

    for idx in indices:
        os.remove(webps[idx])

    logger.info("Deleted %d image pages from %s", len(indices), book_dir)
    return total_pages - len(indices)
