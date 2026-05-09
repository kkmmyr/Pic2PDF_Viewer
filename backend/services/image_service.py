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


def reorder_book_image_pages(book_dir: str, page_indices: list[int]) -> int:
    """`book_dir` 配下の WebP を `page_indices` の指す順に再採番リネームする。

    Args:
        book_dir: 書籍画像ディレクトリの絶対パス
        page_indices: `[0..N-1]` の完全なパーミュテーション。
            `page_indices[i]` は新しい位置 i に配置する元 WebP の natsort 順インデックス。

    Returns:
        並び替え後の総ページ数（= 元のページ数）

    Raises:
        FileNotFoundError: ディレクトリが存在しない場合
        ValueError: page_indices が `[0..N-1]` のパーミュテーションでない場合

    実装メモ:
        既存のファイル名と新しいファイル名が衝突しうるため、一時名 `__reorder_tmp_NNNN.webp`
        を経由する 2 段階リネーム（旧名→一時名→新名）で安全に並び替える。
        新しいファイル名は `page_0001.webp / page_0002.webp / ...` の 0 詰め採番。
    """
    if not os.path.isdir(book_dir):
        raise FileNotFoundError(f"Book images directory not found: {book_dir}")

    webps = [
        os.path.join(book_dir, f)
        for f in natsorted(os.listdir(book_dir))
        if f.lower().endswith('.webp')
    ]
    total_pages = len(webps)

    if sorted(page_indices) != list(range(total_pages)):
        raise ValueError(
            f"page_indices must be a permutation of [0..{total_pages - 1}], got: {page_indices}"
        )

    # 段階 1: 旧名 → 一時名（page_indices の順序で並べた一時名を割り当てる）
    temp_paths: list[str] = []
    for new_pos, old_idx in enumerate(page_indices):
        tmp_path = os.path.join(book_dir, f"__reorder_tmp_{new_pos:04d}.webp")
        os.rename(webps[old_idx], tmp_path)
        temp_paths.append(tmp_path)

    # 段階 2: 一時名 → 最終名（page_NNNN.webp の 0 詰め採番）
    for new_pos, tmp_path in enumerate(temp_paths):
        final_path = os.path.join(book_dir, f"page_{new_pos + 1:04d}.webp")
        os.rename(tmp_path, final_path)

    logger.info("Reordered %d image pages in %s", total_pages, book_dir)
    return total_pages
