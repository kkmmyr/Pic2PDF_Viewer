import os
import shutil
from utils.file_naming import get_thumbnail_name
from utils.file_utils import is_pdf_file
from utils.logger import get_logger

logger = get_logger(__name__)


class FileManager:
    """PDF・サムネイル・画像ディレクトリの3点セット操作を一元管理する。

    各メソッドは失敗時に自動ロールバックを行う。
    ロールバック自体が失敗した場合はログに記録し続行する。
    """

    @staticmethod
    def move_with_assets(
        item: str,
        src_path: str,
        dst_path: str,
        dirs: dict,
    ) -> None:
        """PDF（またはフォルダ）とサムネイル・画像ディレクトリを移動する。

        Args:
            item: 移動対象のファイル名またはフォルダ名
            src_path: 移動元の相対パス
            dst_path: 移動先の相対パス
            dirs: get_dirs_by_source() が返す辞書 (pdf/thumb/img キーを持つ)

        Raises:
            FileNotFoundError: 移動元が存在しない場合
            FileExistsError: 移動先が既に存在する場合
            OSError: 移動操作に失敗した場合（ロールバック後に再 raise）
        """
        moved_parts: list[tuple[str, str]] = []  # (移動先, 移動元) — ロールバック用

        src_pdf = os.path.join(dirs["pdf"], src_path, item)
        dst_pdf = os.path.join(dirs["pdf"], dst_path, item)

        if not os.path.exists(src_pdf):
            raise FileNotFoundError(f"Item not found: {item}")
        if os.path.exists(dst_pdf):
            raise FileExistsError(f"Destination exists: {item}")

        try:
            os.makedirs(os.path.dirname(dst_pdf), exist_ok=True)
            shutil.move(src_pdf, dst_pdf)
            moved_parts.append((dst_pdf, src_pdf))

            # サムネイルを移動
            if os.path.isdir(dst_pdf):
                src_thumb = os.path.join(dirs["thumb"], src_path, item)
                dst_thumb = os.path.join(dirs["thumb"], dst_path, item)
            else:
                thumb_name = get_thumbnail_name(item)
                src_thumb = os.path.join(dirs["thumb"], src_path, thumb_name)
                dst_thumb = os.path.join(dirs["thumb"], dst_path, thumb_name)

            if os.path.exists(src_thumb):
                os.makedirs(os.path.dirname(dst_thumb), exist_ok=True)
                shutil.move(src_thumb, dst_thumb)
                moved_parts.append((dst_thumb, src_thumb))

            # 画像ディレクトリを移動
            book_name = os.path.splitext(item)[0] if is_pdf_file(item) else item
            src_img = os.path.join(dirs["img"], src_path, book_name)
            dst_img = os.path.join(dirs["img"], dst_path, book_name)

            if os.path.exists(src_img):
                os.makedirs(os.path.dirname(dst_img), exist_ok=True)
                shutil.move(src_img, dst_img)
                moved_parts.append((dst_img, src_img))

        except Exception as e:
            for moved_dst, original_src in reversed(moved_parts):
                try:
                    shutil.move(moved_dst, original_src)
                except Exception as rollback_err:
                    logger.error("Rollback failed: %s -> %s: %s", moved_dst, original_src, rollback_err)
            raise OSError(f"Error moving {item}: {e}") from e

    @staticmethod
    def rename_with_assets(
        path: str,
        old_name: str,
        new_name: str,
        is_folder: bool,
        dirs: dict,
    ) -> None:
        """PDF（またはフォルダ）とサムネイル・画像ディレクトリをリネームする。

        Args:
            path: 対象の相対パス
            old_name: 変更前の名前
            new_name: 変更後の名前
            is_folder: フォルダの場合 True、PDFファイルの場合 False
            dirs: get_dirs_by_source() が返す辞書 (pdf/thumb/img キーを持つ)

        Raises:
            FileNotFoundError: 変更前のファイルが存在しない場合
            FileExistsError: 変更後の名前が既に存在する場合
            OSError: リネーム操作に失敗した場合（ロールバック後に再 raise）
        """
        renamed_parts: list[tuple[str, str]] = []  # (変更後, 変更前) — ロールバック用

        src = os.path.join(dirs["pdf"], path, old_name)
        dst = os.path.join(dirs["pdf"], path, new_name)

        if not os.path.exists(src):
            raise FileNotFoundError(f"Item not found: {old_name}")
        if os.path.exists(dst):
            raise FileExistsError(f"Name already exists: {new_name}")

        try:
            os.rename(src, dst)
            renamed_parts.append((dst, src))

            if is_folder:
                for base_dir in (dirs["thumb"], dirs["img"]):
                    old_sub = os.path.join(base_dir, path, old_name)
                    new_sub = os.path.join(base_dir, path, new_name)
                    if os.path.exists(old_sub):
                        os.rename(old_sub, new_sub)
                        renamed_parts.append((new_sub, old_sub))
            else:
                old_thumb = os.path.join(dirs["thumb"], path, get_thumbnail_name(old_name))
                new_thumb = os.path.join(dirs["thumb"], path, get_thumbnail_name(new_name))
                if os.path.exists(old_thumb):
                    os.rename(old_thumb, new_thumb)
                    renamed_parts.append((new_thumb, old_thumb))

                old_img = os.path.join(dirs["img"], path, os.path.splitext(old_name)[0])
                new_img = os.path.join(dirs["img"], path, os.path.splitext(new_name)[0])
                if os.path.exists(old_img):
                    os.rename(old_img, new_img)
                    renamed_parts.append((new_img, old_img))

        except Exception as e:
            for renamed_dst, original_src in reversed(renamed_parts):
                try:
                    os.rename(renamed_dst, original_src)
                except Exception as rollback_err:
                    logger.error("Rollback failed: %s -> %s: %s", renamed_dst, original_src, rollback_err)
            raise OSError(f"Rename failed: {e}") from e

    @staticmethod
    def delete_with_assets(item: str, path: str, dirs: dict) -> None:
        """PDF・サムネイル・画像ディレクトリをディスクから完全削除する。

        Args:
            item: 削除対象の PDF ファイル名
            path: 対象の相対パス
            dirs: get_dirs_by_source() が返す辞書 (pdf/thumb/img キーを持つ)

        Raises:
            FileNotFoundError: PDF ファイルが存在しない場合
            OSError: 削除操作に失敗した場合
        """
        pdf_path = os.path.join(dirs["pdf"], path, item) if path else os.path.join(dirs["pdf"], item)
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"Item not found: {item}")

        os.remove(pdf_path)

        thumb_name = get_thumbnail_name(item)
        thumb_path = (
            os.path.join(dirs["thumb"], path, thumb_name) if path
            else os.path.join(dirs["thumb"], thumb_name)
        )
        if os.path.exists(thumb_path):
            try:
                os.remove(thumb_path)
            except Exception as e:
                logger.warning("Failed to delete thumbnail %s: %s", thumb_path, e)

        book_name = os.path.splitext(item)[0]
        img_dir = (
            os.path.join(dirs["img"], path, book_name) if path
            else os.path.join(dirs["img"], book_name)
        )
        if os.path.exists(img_dir):
            try:
                shutil.rmtree(img_dir)
            except Exception as e:
                logger.warning("Failed to delete image dir %s: %s", img_dir, e)
