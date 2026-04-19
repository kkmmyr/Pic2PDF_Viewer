import os


def get_thumbnail_name(pdf_name: str) -> str:
    """PDF ファイル名に対応するサムネイルファイル名を返す。"""
    return os.path.splitext(pdf_name)[0] + ".jpg"
