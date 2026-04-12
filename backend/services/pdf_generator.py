import os
import img2pdf
import zipfile
import io
import shutil
from natsort import natsorted
from PIL import Image
from typing import Optional, Callable, Union


def generate_thumbnail(image_data_or_path: Union[bytes, str], output_path: str) -> None:
    try:
        if isinstance(image_data_or_path, bytes):
            img = Image.open(io.BytesIO(image_data_or_path))
        else:
            img = Image.open(image_data_or_path)

        # Resize to height 500px, keeping aspect ratio
        base_height = 500
        h_percent = base_height / float(img.size[1])
        w_size = int(float(img.size[0]) * h_percent)
        img = img.resize((w_size, base_height), Image.Resampling.LANCZOS)

        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        img.save(output_path, "JPEG")
        print(f"Generated thumbnail: {output_path}")
    except Exception as e:
        print(f"Failed to generate thumbnail {output_path}: {e}")


class PdfGenerator:
    def __init__(self, output_dir: str, thumbnail_dir: str, images_dir: str, complete_dir: str,
                 compressed_output_dir: Optional[str] = None, quality: Optional[int] = None,
                 progress_callback: Optional[Callable[[str], None]] = None):
        self.output_dir = output_dir
        self.thumbnail_dir = thumbnail_dir
        self.images_dir = images_dir
        self.complete_dir = complete_dir
        self.compressed_output_dir = compressed_output_dir
        self.quality = quality
        self.progress_callback = progress_callback
        self.generated_files: list[str] = []
        self.moves: list[tuple[str, str, bool]] = []  # (src, dst, is_dir)

    # ------------------------------------------------------------------
    # 共通: サムネイル・PDF・圧縮PDF を一括生成してファイル名を記録する
    # ------------------------------------------------------------------
    def _generate_outputs(
        self,
        item_name: str,
        images: list,
        thumb_source: Union[bytes, str],
    ) -> str:
        """
        サムネイル生成・PDF生成・圧縮PDF生成の共通処理。

        Args:
            item_name: 出力ファイルのベース名 (拡張子なし)
            images: PDF化する画像のリスト (bytes または ファイルパス)
            thumb_source: サムネイル生成に使う最初の画像 (bytes または パス)

        Returns:
            生成した PDF のフルパス
        """
        pdf_filename = f"{item_name}.pdf"
        output_path = os.path.join(self.output_dir, pdf_filename)
        thumb_path = os.path.join(self.thumbnail_dir, f"{item_name}.jpg")

        generate_thumbnail(thumb_source, thumb_path)
        self._create_pdf_file(images, output_path)
        self._create_compressed_pdf(images, pdf_filename)
        self.generated_files.append(pdf_filename)
        return output_path

    # ------------------------------------------------------------------
    # ZIP 処理
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
                    [f for f in zf.namelist() if f.lower().endswith('.webp')]
                )
                if not webp_in_zip:
                    return

                # 画像データ読み込み & images_dir へ保存
                image_data_list: list[bytes] = []
                for i, image_name in enumerate(webp_in_zip):
                    with zf.open(image_name) as image_file:
                        data = image_file.read()
                    image_data_list.append(data)

                    image_out_path = os.path.join(target_images_dir, image_name)
                    os.makedirs(os.path.dirname(image_out_path), exist_ok=True)
                    with open(image_out_path, "wb") as img_f:
                        img_f.write(data)

            output_path = self._generate_outputs(item_name, image_data_list, image_data_list[0])
            print(f"Generated from ZIP: {output_path}")
            self.moves.append((zip_path, os.path.join(self.complete_dir, zip_filename), False))

        except Exception as e:
            print(f"Failed to generate PDF for ZIP {zip_path}: {e}")

    # ------------------------------------------------------------------
    # ディレクトリ処理
    # ------------------------------------------------------------------
    def process_directory(self, root: str, webp_files: list[str], is_root: bool) -> None:
        folder_name = os.path.basename(root)

        if self.progress_callback:
            self.progress_callback(folder_name)

        webp_files = natsorted(webp_files)
        image_paths = [os.path.join(root, f) for f in webp_files]

        target_images_dir = os.path.join(self.images_dir, folder_name)
        os.makedirs(target_images_dir, exist_ok=True)

        try:
            # images_dir へコピー
            for img_path, img_name in zip(image_paths, webp_files):
                shutil.copy2(img_path, os.path.join(target_images_dir, img_name))

            output_path = self._generate_outputs(
                folder_name, image_paths, image_paths[0] if image_paths else b''
            )
            print(f"Generated from Folder: {output_path}")

            # 移動スケジュール
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
            print(f"Failed to generate PDF for folder {root}: {e}")

    # ------------------------------------------------------------------
    # 圧縮 PDF 生成 (内部ヘルパー)
    # ------------------------------------------------------------------
    def _create_compressed_pdf(self, images: list, pdf_filename: str) -> None:
        """圧縮版PDFが有効な場合に compressed_output_dir へ出力する。"""
        if not (self.compressed_output_dir and self.quality):
            return
        compressed_path = os.path.join(self.compressed_output_dir, pdf_filename)
        self._create_pdf_file(images, compressed_path, quality=self.quality)
        print(f"Generated compressed PDF: {compressed_path}")

    def _create_pdf_file(self, images: list, output_path: str, quality: Optional[int] = None) -> None:
        """画像データ (bytes) またはパスのリストから PDF を生成する。"""
        if quality:
            processed: list[bytes] = []
            for item in images:
                img = Image.open(io.BytesIO(item)) if isinstance(item, bytes) else Image.open(item)
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=quality)
                processed.append(buf.getvalue())
            with open(output_path, "wb") as f:
                f.write(img2pdf.convert(processed))
        else:
            with open(output_path, "wb") as f:
                f.write(img2pdf.convert(images))

    # ------------------------------------------------------------------
    # ファイル移動 (バックアップ＋ロールバック付き)
    # ------------------------------------------------------------------
    def execute_moves(self) -> None:
        for src, dst, is_dir in self.moves:
            backup_path = None
            try:
                if os.path.exists(dst):
                    backup_path = dst + ".__bak__"
                    shutil.move(dst, backup_path)

                shutil.move(src, dst)
                print(f"Moved {'folder' if is_dir else 'file'} to: {dst}")

                if backup_path and os.path.exists(backup_path):
                    if os.path.isdir(backup_path):
                        shutil.rmtree(backup_path)
                    else:
                        os.remove(backup_path)

            except Exception as e:
                print(f"Failed to move {src} to {dst}: {e}")
                if backup_path and os.path.exists(backup_path):
                    try:
                        shutil.move(backup_path, dst)
                        print(f"Restored backup: {dst}")
                    except Exception as restore_err:
                        print(f"Failed to restore backup {backup_path}: {restore_err}")

    # ------------------------------------------------------------------
    # エントリポイント
    # ------------------------------------------------------------------
    def run(self, source_dir: str) -> list[str]:
        cleanups: list[str] = []

        for root, dirs, files in os.walk(source_dir, topdown=False):
            for zip_filename in [f for f in files if f.lower().endswith('.zip')]:
                self.process_zip(root, zip_filename)

            webp_files = [f for f in files if f.lower().endswith('.webp')]
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
                        print(f"Removed empty directory: {folder}")
                except Exception as e:
                    print(f"Failed to remove directory {folder}: {e}")

        return self.generated_files


def scan_and_generate(
    source_dir: str,
    output_dir: str,
    thumbnail_dir: str,
    images_dir: str,
    complete_dir: str,
    compressed_output_dir: Optional[str] = None,
    quality: Optional[int] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> list[str]:
    """
    後方互換ラッパー。source_dir 内の WebP/ZIP を PDF に変換する。
    """
    generator = PdfGenerator(
        output_dir, thumbnail_dir, images_dir, complete_dir,
        compressed_output_dir, quality, progress_callback
    )
    return generator.run(source_dir)
