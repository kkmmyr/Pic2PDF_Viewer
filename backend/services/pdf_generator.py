import os
import img2pdf
import zipfile
import io
import shutil
from natsort import natsorted
from PIL import Image
from typing import Optional, Callable
from config import THUMBNAIL_HEIGHT
from utils.file_utils import is_webp_file, is_zip_file
from utils.logger import get_logger

logger = get_logger(__name__)


def generate_thumbnail(image_path: str, output_path: str) -> None:
    try:
        img = Image.open(image_path)
        h_percent = THUMBNAIL_HEIGHT / float(img.size[1])
        w_size = int(float(img.size[0]) * h_percent)
        img = img.resize((w_size, THUMBNAIL_HEIGHT), Image.Resampling.LANCZOS)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(output_path, "JPEG")
        logger.info("Generated thumbnail: %s", output_path)
    except Exception as e:
        logger.error("Failed to generate thumbnail %s: %s", output_path, e)


def _collect_images(images_dir: str) -> list[str]:
    """ディレクトリ内の WebP 画像を自然順で収集する。"""
    files = [f for f in os.listdir(images_dir) if is_webp_file(f)]
    return [os.path.join(images_dir, f) for f in natsorted(files)]


class PdfGenerator:
    def __init__(self, output_dir: str, thumbnail_dir: str, images_dir: str, complete_dir: str,
                 progress_callback: Optional[Callable[[str], None]] = None):
        self.output_dir = output_dir
        self.thumbnail_dir = thumbnail_dir
        self.images_dir = images_dir
        self.complete_dir = complete_dir
        self.progress_callback = progress_callback
        self.generated_files: list[str] = []
        self.moves: list[tuple[str, str, bool]] = []

    # ------------------------------------------------------------------
    # 共通: images_dir に収集済みの画像から PDF・サムネイルを生成
    # ------------------------------------------------------------------
    def _generate_outputs(self, item_name: str, item_images_dir: str) -> str:
        image_paths = _collect_images(item_images_dir)
        if not image_paths:
            raise ValueError(f"No images found in {item_images_dir}")

        pdf_filename = f"{item_name}.pdf"
        output_path = os.path.join(self.output_dir, pdf_filename)
        thumb_path = os.path.join(self.thumbnail_dir, f"{item_name}.jpg")

        generate_thumbnail(image_paths[0], thumb_path)
        self._create_pdf_file(image_paths, output_path)
        self.generated_files.append(pdf_filename)
        return output_path

    # ------------------------------------------------------------------
    # ZIP 処理: images_dir に展開 → 共通フローへ
    # ------------------------------------------------------------------
    def process_zip(self, root: str, zip_filename: str) -> None:
        item_name = os.path.splitext(zip_filename)[0]
        zip_path = os.path.join(root, zip_filename)

        if not os.path.exists(zip_path):
            return

        if self.progress_callback:
            self.progress_callback(item_name)

        target_images_dir = os.path.join(self.images_dir, item_name)
        os.makedirs(target_images_dir, exist_ok=True)

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                webp_in_zip = natsorted(
                    [f for f in zf.namelist() if is_webp_file(f)]
                )
                if not webp_in_zip:
                    return

                for image_name in webp_in_zip:
                    with zf.open(image_name) as image_file:
                        data = image_file.read()
                    image_out_path = os.path.join(target_images_dir, os.path.basename(image_name))
                    with open(image_out_path, "wb") as img_f:
                        img_f.write(data)

            output_path = self._generate_outputs(item_name, target_images_dir)
            logger.info("Generated from ZIP: %s", output_path)
            self.moves.append((zip_path, os.path.join(self.complete_dir, zip_filename), False))

        except Exception as e:
            logger.error("Failed to generate PDF for ZIP %s: %s", zip_path, e)

    # ------------------------------------------------------------------
    # ディレクトリ処理: images_dir にコピー → 共通フローへ
    # ------------------------------------------------------------------
    def process_directory(self, root: str, webp_files: list[str], is_root: bool) -> None:
        folder_name = os.path.basename(root)

        if self.progress_callback:
            self.progress_callback(folder_name)

        target_images_dir = os.path.join(self.images_dir, folder_name)
        os.makedirs(target_images_dir, exist_ok=True)

        try:
            for img_name in webp_files:
                shutil.copy2(os.path.join(root, img_name), os.path.join(target_images_dir, img_name))

            output_path = self._generate_outputs(folder_name, target_images_dir)
            logger.info("Generated from Folder: %s", output_path)

            if not is_root:
                self.moves.append((root, os.path.join(self.complete_dir, folder_name), True))
            else:
                for f in webp_files:
                    self.moves.append((
                        os.path.join(root, f),
                        os.path.join(self.complete_dir, f),
                        False
                    ))

        except Exception as e:
            logger.error("Failed to generate PDF for folder %s: %s", root, e)

    def _create_pdf_file(self, image_paths: list[str], output_path: str, quality: Optional[int] = None) -> None:
        if quality:
            processed: list[bytes] = []
            for item in image_paths:
                img = Image.open(item)
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=quality)
                processed.append(buf.getvalue())
            with open(output_path, "wb") as f:
                f.write(img2pdf.convert(processed))
        else:
            with open(output_path, "wb") as f:
                f.write(img2pdf.convert(image_paths))

    # ------------------------------------------------------------------
    # ファイル移動（バックアップ＋ロールバック）
    # ------------------------------------------------------------------
    def execute_moves(self) -> None:
        for src, dst, is_dir in self.moves:
            backup_path = None
            try:
                if os.path.exists(dst):
                    backup_path = dst + ".__bak__"
                    shutil.move(dst, backup_path)

                shutil.move(src, dst)
                logger.info("Moved %s to: %s", "folder" if is_dir else "file", dst)

                if backup_path and os.path.exists(backup_path):
                    if os.path.isdir(backup_path):
                        shutil.rmtree(backup_path)
                    else:
                        os.remove(backup_path)

            except Exception as e:
                logger.error("Failed to move %s to %s: %s", src, dst, e)
                if backup_path and os.path.exists(backup_path):
                    try:
                        shutil.move(backup_path, dst)
                        logger.info("Restored backup: %s", dst)
                    except Exception as restore_err:
                        logger.error("Failed to restore backup %s: %s", backup_path, restore_err)

    # ------------------------------------------------------------------
    # エントリポイント
    # ------------------------------------------------------------------
    def run(self, source_dir: str) -> list[str]:
        cleanups: list[str] = []

        for root, dirs, files in os.walk(source_dir, topdown=False):
            for zip_filename in [f for f in files if is_zip_file(f)]:
                self.process_zip(root, zip_filename)

            webp_files = [f for f in files if is_webp_file(f)]
            if webp_files:
                self.process_directory(root, webp_files, is_root=(root == source_dir))

            if root != source_dir:
                cleanups.append(root)

        self.execute_moves()

        for folder in cleanups:
            if os.path.exists(folder):
                try:
                    if not os.listdir(folder):
                        os.rmdir(folder)
                        logger.info("Removed empty directory: %s", folder)
                except Exception as e:
                    logger.error("Failed to remove directory %s: %s", folder, e)

        return self.generated_files


def scan_and_generate(
    source_dir: str,
    output_dir: str,
    thumbnail_dir: str,
    images_dir: str,
    complete_dir: str,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> list[str]:
    """source_dir 内の WebP/ZIP を PDF に変換する。"""
    generator = PdfGenerator(
        output_dir, thumbnail_dir, images_dir, complete_dir, progress_callback
    )
    return generator.run(source_dir)


def batch_compress(
    images_dir: str,
    output_dir: str,
    quality: int,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> list[str]:
    """
    images_dir 配下の各サブフォルダを走査し、WebP 画像から圧縮 PDF を生成する。

    既に output_dir に同名 PDF が存在する場合はスキップする。

    Args:
        images_dir: 走査対象のディレクトリ（通常 IMAGES_DIR）
        output_dir: 圧縮 PDF の出力先（通常 PDF_COMPRESSED_DIR）
        quality: JPEG 品質（10〜95）
        progress_callback: 処理中のフォルダ相対パスを通知するコールバック

    Returns:
        生成した PDF の相対パスリスト
    """
    # PdfGenerator の private API に依存しないため、PIL/img2pdf を直接使う最小実装。
    generated: list[str] = []
    for root, _, files in os.walk(images_dir):
        webp_files = [f for f in files if is_webp_file(f)]
        if not webp_files:
            continue

        rel_path = os.path.relpath(root, images_dir)
        folder_name = os.path.basename(root)

        if progress_callback:
            progress_callback(f"Batch: {rel_path}")

        webp_files = natsorted(webp_files)
        image_paths = [os.path.join(root, f) for f in webp_files]

        pdf_filename = f"{folder_name}.pdf"
        if rel_path == ".":
            target_output_dir = output_dir
        else:
            target_output_dir = os.path.join(output_dir, os.path.dirname(rel_path))
        os.makedirs(target_output_dir, exist_ok=True)
        output_path = os.path.join(target_output_dir, pdf_filename)

        if os.path.exists(output_path):
            logger.info("Skipping already compressed: %s", output_path)
            continue

        # 内部ヘルパー: 品質指定で JPEG 化 → img2pdf
        processed: list[bytes] = []
        for item in image_paths:
            img = Image.open(item)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            processed.append(buf.getvalue())
        with open(output_path, "wb") as f:
            f.write(img2pdf.convert(processed))

        rel_pdf = os.path.join(rel_path, pdf_filename) if rel_path != "." else pdf_filename
        generated.append(rel_pdf)
        logger.info("Batch compressed: %s", output_path)

    return generated
