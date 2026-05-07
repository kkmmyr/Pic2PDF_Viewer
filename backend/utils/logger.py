"""
アプリケーション共通ロガー。

各モジュールでは以下のように使用する:
    from utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("処理完了")

設計判断は ADR-0006 を参照（出力先 / ローテーション戦略 / セキュリティ含む）。
- StreamHandler: 各モジュール logger に直接付与（開発時の即時可視性）
- RotatingFileHandler: root logger に 1 度だけ付与（10MB × 5 世代、UTF-8）
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# backend/data/logs/app.log（backend/data/ は .gitignore 済み）
_LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "logs",
)
_LOG_FILE = os.path.join(_LOG_DIR, "app.log")
_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_LOG_BACKUP_COUNT = 5

_FORMATTER = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# RotatingFileHandler 重複登録の検知用マーカー
_FILE_HANDLER_MARKER = "_pic2pdf_app_log_handler"


def _ensure_root_file_handler() -> None:
    """
    root logger に RotatingFileHandler を 1 度だけ追加する。

    各モジュール logger の `propagate=True`（デフォルト）に乗せて root に流す。
    ファイルハンドルを 1 個に集約することで Windows でのローテーション競合を回避する。
    """
    root = logging.getLogger()
    for handler in root.handlers:
        if getattr(handler, _FILE_HANDLER_MARKER, False):
            return

    os.makedirs(_LOG_DIR, exist_ok=True)
    file_handler = RotatingFileHandler(
        _LOG_FILE,
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(_FORMATTER)
    setattr(file_handler, _FILE_HANDLER_MARKER, True)
    root.addHandler(file_handler)

    # サードパーティ DEBUG が混入しないよう root の閾値は WARNING に絞る。
    # 各モジュール logger は INFO のため、自前ログは INFO 以上が file に書かれる。
    if root.level == logging.NOTSET or root.level > logging.WARNING:
        root.setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    指定した名前のロガーを返す。

    - ルートロガーではなくモジュール単位のロガーを使用し、
      ログレベルの細かい制御を可能にする。
    - StreamHandler の二重登録を防ぐため、handlers 未設定の場合のみ追加。
    - RotatingFileHandler は root logger に 1 度だけ追加され、
      `propagate=True` 経由で全 logger のログがファイルに書かれる。
    """
    _ensure_root_file_handler()

    logger = logging.getLogger(name)
    if not logger.handlers:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(_FORMATTER)
        logger.addHandler(stream_handler)

    logger.setLevel(logging.INFO)
    return logger
