class FileOperationError(Exception):
    """ファイル操作（移動・リネーム・削除）に失敗した場合の例外。"""


class OcrProcessError(Exception):
    """OCRプロセスの起動・停止に失敗した場合の例外。"""


class AutoFillError(Exception):
    """サークル名自動登録処理に失敗した場合の例外。"""
