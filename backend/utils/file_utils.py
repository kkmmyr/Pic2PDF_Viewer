"""ファイル種別判定ユーティリティ。"""
from config import SUPPORTED_IMAGE_FORMATS, SUPPORTED_WEBP_FORMAT, SUPPORTED_ZIP_FORMAT


def is_webp_file(name: str) -> bool:
    return name.lower().endswith(SUPPORTED_WEBP_FORMAT)


def is_zip_file(name: str) -> bool:
    return name.lower().endswith(SUPPORTED_ZIP_FORMAT)


def is_image_file(name: str) -> bool:
    return name.lower().endswith(SUPPORTED_IMAGE_FORMATS)


def is_pdf_file(name: str) -> bool:
    return name.lower().endswith(".pdf")
