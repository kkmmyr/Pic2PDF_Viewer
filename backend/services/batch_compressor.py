"""既存画像から一括で圧縮 PDF を生成するサービス。

`PdfGenerator`（生成 + 移動 + ロールバック）と独立した処理として分離した。
PdfGenerator の private API には依存せず、PIL/img2pdf を直接使う最小実装。
"""
import io
import os
from collections.abc import Callable

import img2pdf
from natsort import natsorted
from PIL import Image

from utils.file_utils import is_webp_file
from utils.logger import get_logger

logger = get_logger(__name__)


def _write_compressed_pdf(image_paths: list[str], output_path: str, quality: int) -> None:
    """画像を指定品質で JPEG 変換し img2pdf で 1 PDF に書き出す。"""
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


def batch_compress(
    images_dir: str,
    output_dir: str,
    quality: int,
    progress_callback: Callable[[str], None] | None = None,
) -> list[str]:
    """`images_dir` 配下の各サブフォルダを走査し、WebP 画像から圧縮 PDF を生成する。

    既に `output_dir` に同名 PDF が存在する場合はスキップする。

    Args:
        images_dir: 走査対象のディレクトリ（通常 IMAGES_DIR）
        output_dir: 圧縮 PDF の出力先（通常 PDF_COMPRESSED_DIR）
        quality: JPEG 品質（10〜95）
        progress_callback: 処理中のフォルダ相対パスを通知するコールバック

    Returns:
        生成した PDF の相対パスリスト
    """
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

        _write_compressed_pdf(image_paths, output_path, quality)

        rel_pdf = os.path.join(rel_path, pdf_filename) if rel_path != "." else pdf_filename
        generated.append(rel_pdf)
        logger.info("Batch compressed: %s", output_path)

    return generated
