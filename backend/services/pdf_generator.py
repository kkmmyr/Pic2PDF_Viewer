import os
import shutil
import zipfile
from collections.abc import Callable
from typing import NamedTuple

import img2pdf
from natsort import natsorted
from PIL import Image

from config import (
    THUMBNAIL_HEIGHT,
    ZIP_MAX_ENTRIES,
    ZIP_MAX_PER_FILE_BYTES,
    ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES,
)
from services.batch_compressor import batch_compress  # 後方互換 re-export
from utils.file_utils import is_webp_file, is_zip_file
from utils.logger import get_logger

logger = get_logger(__name__)

__all__ = ["generate_thumbnail", "PdfGenerator", "scan_and_generate", "batch_compress", "GenerateResult"]


class GenerateResult(NamedTuple):
    """`scan_and_generate` の戻り値。

    - `generated`: 正常生成された書籍ファイル名（".pdf" 付き）のリスト
    - `failed_items`: 失敗した書籍とエラーメッセージの組 `(item_name, error_msg)`
    """

    generated: list[str]
    failed_items: list[tuple[str, str]]


def generate_thumbnail(image_path: str, output_path: str) -> bool:
    """画像ファイル（WebP / JPEG / PNG など PIL が読める形式）からサムネイル JPG を生成する。

    fitz は WebP を読めないため、generated ソース（image-only モード）の
    サムネイル生成・再生成はこの関数を使う必要がある。PDF からの生成は
    `services.thumbnail_service.ThumbnailService.generate_thumbnail` を使う。

    Returns:
        生成に成功した場合 True、失敗時は False（例外はキャッチしてログ出力）
    """
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        img = Image.open(image_path)
        h_percent = THUMBNAIL_HEIGHT / float(img.size[1])
        w_size = int(float(img.size[0]) * h_percent)
        img = img.resize((w_size, THUMBNAIL_HEIGHT), Image.Resampling.LANCZOS)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(output_path, "JPEG")
        logger.info("Generated thumbnail: %s", output_path)
        return True
    except Exception as e:
        logger.error("Failed to generate thumbnail %s: %s", output_path, e)
        return False


def _sanitize_fs_name(name: str) -> str:
    """Windows ファイルシステムで問題になる末尾のドット・スペースを除去する。

    Windows の CreateDirectoryW（makedirs）は末尾のドット・スペースを自動除去するが、
    CreateFileW（open / shutil.copy2）の中間パス解決では除去されない。
    makedirs で作成されるフォルダ名と copy2 で参照するパスが不一致になり
    FileNotFoundError が発生するため、事前に正規化する。
    """
    return name.rstrip(". ")


def _collect_images(images_dir: str) -> list[str]:
    """ディレクトリ内の WebP 画像を自然順で収集する。"""
    files = [f for f in os.listdir(images_dir) if is_webp_file(f)]
    return [os.path.join(images_dir, f) for f in natsorted(files)]


def _check_zip_safety(webp_infos: list[zipfile.ZipInfo], zip_filename: str) -> None:
    """ZIP 内 WebP エントリのサイズ／件数が上限以内かを検査する（zip bomb 対策）。

    超過時は ValueError を投げ、呼び出し側の except 節で `failed_items` に集約させる。
    違反検出時は `logger.warning` で監査用ログ（`Security: ...` プレフィックス）も残し、
    一般的な I/O エラー (`logger.error("Failed to generate PDF for ZIP %s ...")`)
    と区別できるようにする。
    """

    def _reject(reason: str) -> None:
        logger.warning("Security: ZIP rejected (%s) — %s", zip_filename, reason)
        raise ValueError(reason)

    if len(webp_infos) > ZIP_MAX_ENTRIES:
        _reject(f"entry count {len(webp_infos)} exceeds limit {ZIP_MAX_ENTRIES}")
    total = 0
    for info in webp_infos:
        if info.file_size > ZIP_MAX_PER_FILE_BYTES:
            _reject(
                f"entry {os.path.basename(info.filename)!r} uncompressed size "
                f"{info.file_size} exceeds per-file limit {ZIP_MAX_PER_FILE_BYTES}"
            )
        total += info.file_size
        if total > ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES:
            _reject(f"total uncompressed size exceeds limit {ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES}")


class PdfGenerator:
    def __init__(
        self,
        output_dir: str | None,
        thumbnail_dir: str,
        images_dir: str,
        complete_dir: str,
        progress_callback: Callable[[str], None] | None = None,
    ):
        self.output_dir = output_dir  # None = image-only モード（PDF 生成をスキップ）
        self.thumbnail_dir = thumbnail_dir
        self.images_dir = images_dir
        self.complete_dir = complete_dir
        self.progress_callback = progress_callback
        self.generated_files: list[str] = []
        self.moves: list[tuple[str, str, bool]] = []
        # サイレント失敗を防ぐため、process_zip / process_directory の例外をここに集約する
        self.failed_items: list[tuple[str, str]] = []

    # ------------------------------------------------------------------
    # 共通: images_dir に収集済みの画像から PDF・サムネイルを生成
    # ------------------------------------------------------------------
    def _generate_outputs(self, item_name: str, item_images_dir: str) -> str:
        image_paths = _collect_images(item_images_dir)
        if not image_paths:
            raise ValueError(f"No images found in {item_images_dir}")

        pdf_filename = f"{item_name}.pdf"
        thumb_path = os.path.join(self.thumbnail_dir, f"{item_name}.jpg")

        generate_thumbnail(image_paths[0], thumb_path)
        if self.output_dir is not None:
            output_path = os.path.join(self.output_dir, pdf_filename)
            self._create_pdf_file(image_paths, output_path)

        self.generated_files.append(pdf_filename)
        return pdf_filename

    # ------------------------------------------------------------------
    # ZIP 処理: images_dir に展開 → 共通フローへ
    # ------------------------------------------------------------------
    def process_zip(self, root: str, zip_filename: str) -> None:
        item_name = _sanitize_fs_name(os.path.splitext(zip_filename)[0])
        zip_path = os.path.join(root, zip_filename)

        if not os.path.exists(zip_path):
            return

        if self.progress_callback:
            self.progress_callback(item_name)

        target_images_dir = os.path.join(self.images_dir, item_name)
        os.makedirs(target_images_dir, exist_ok=True)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                webp_infos = [info for info in zf.infolist() if is_webp_file(info.filename)]
                if not webp_infos:
                    return

                # zip bomb 対策: 解凍前に WebP エントリの件数・サイズを検査
                _check_zip_safety(webp_infos, zip_filename)

                webp_infos = natsorted(webp_infos, key=lambda i: i.filename)

                for info in webp_infos:
                    with zf.open(info) as image_file:
                        data = image_file.read()
                    image_out_path = os.path.join(target_images_dir, os.path.basename(info.filename))
                    with open(image_out_path, "wb") as img_f:
                        img_f.write(data)

            self._generate_outputs(item_name, target_images_dir)
            logger.info("Generated from ZIP: %s", zip_filename)
            self.moves.append((zip_path, os.path.join(self.complete_dir, zip_filename), False))

        except Exception as e:
            logger.error("Failed to generate PDF for ZIP %s: %s", zip_filename, e)
            self.failed_items.append((item_name, str(e)))

    # ------------------------------------------------------------------
    # ディレクトリ処理: images_dir にコピー → 共通フローへ
    # ------------------------------------------------------------------
    def process_directory(self, root: str, webp_files: list[str], is_root: bool) -> None:
        folder_name = _sanitize_fs_name(os.path.basename(root))

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
                    self.moves.append((os.path.join(root, f), os.path.join(self.complete_dir, f), False))

        except Exception as e:
            logger.error("Failed to generate PDF for folder %s: %s", folder_name, e)
            self.failed_items.append((folder_name, str(e)))

    def _create_pdf_file(self, image_paths: list[str], output_path: str) -> None:
        with open(output_path, "wb") as f:
            f.write(img2pdf.convert(image_paths))  # type: ignore[arg-type]

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

        for root, _dirs, files in os.walk(source_dir, topdown=False):
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
    output_dir: str | None,
    thumbnail_dir: str,
    images_dir: str,
    complete_dir: str,
    progress_callback: Callable[[str], None] | None = None,
) -> GenerateResult:
    """source_dir 内の WebP/ZIP を処理し、生成成功・失敗を `GenerateResult` として返す。

    `output_dir=None` を渡すと PDF 生成をスキップ（image-only モード）。
    例外で失敗した書籍は `result.failed_items` に集約され、ジョブ結果として可視化される。
    """
    generator = PdfGenerator(output_dir, thumbnail_dir, images_dir, complete_dir, progress_callback)
    generated = generator.run(source_dir)
    return GenerateResult(generated=generated, failed_items=generator.failed_items)
