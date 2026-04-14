"""
アプリケーション共通ロガー。

各モジュールでは以下のように使用する:
    from utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("処理完了")
"""
import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """
    指定した名前のロガーを返す。

    - ルートロガーではなくモジュール単位のロガーを使用し、
      ログレベルの細かい制御を可能にする。
    - ハンドラーが未設定の場合のみ追加して二重登録を防ぐ。
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(handler)

    logger.setLevel(logging.INFO)
    return logger
