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
        img_src = os.path.join(dirs["img"], path, os.path.splitext(old_name)[0])

        # 存在チェック: PDF または images ディレクトリのどちらか一方が存在すれば OK
        if not os.path.exists(src) and not os.path.exists(img_src):
            raise FileNotFoundError(f"Item not found: {old_name}")
        if os.path.exists(dst):
            raise FileExistsError(f"Name already exists: {new_name}")

        try:
            if os.path.exists(src):
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
        book_name = os.path.splitext(item)[0]
        img_dir = (
            os.path.join(dirs["img"], path, book_name) if path
            else os.path.join(dirs["img"], book_name)
        )

        # 存在チェック: PDF または images ディレクトリのどちらか一方が存在すれば OK
        if not os.path.exists(pdf_path) and not os.path.exists(img_dir):
            raise FileNotFoundError(f"Item not found: {item}")

        # PDF が存在する場合のみ削除（image-only モードでは不在のため skip）
        if os.path.exists(pdf_path):
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

        if os.path.exists(img_dir):
            try:
                shutil.rmtree(img_dir)
            except Exception as e:
                logger.warning("Failed to delete image dir %s: %s", img_dir, e)
