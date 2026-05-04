"""ルーター共通 FastAPI 依存関数・ヘルパー。"""
import functools
from fastapi import HTTPException
from config import VALID_SOURCES
from utils.logger import get_logger
from utils.path_utils import validate_safe_name, validate_safe_path


def validated_source(source: str = "generated") -> str:
    """クエリパラメーター `source` を検証して返す。無効値なら 400 を返す。"""
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail="Invalid source")
    return source


def assert_valid_source(source: str) -> None:
    """リクエストボディの `source` フィールドを検証する。無効値なら 400 を発生させる。"""
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail="Invalid source")


def validate_request_targets(path: str, names: list[str]) -> None:
    """`path` と `names` の各要素を `validate_safe_*` で検証する。

    多くのエンドポイントで重複していた以下のパターンを 1 行に圧縮する:

        validate_safe_path(request.path, param_name="path")
        for name in request.names:
            validate_safe_name(name, param_name="name")
    """
    validate_safe_path(path, param_name="path")
    for name in names:
        validate_safe_name(name, param_name="name")


def log_and_raise_500(operation: str):
    """エンドポイント用デコレータ: 想定外例外を 500 に変換しつつログ記録する。

    ルーター各所で重複していた以下のパターンを集約する:

        try:
            ...
        except Exception as e:
            logger.exception("xxx failed")
            raise HTTPException(status_code=500, detail=str(e))

    挙動:
    - `HTTPException` は素通し（明示的な 4xx を残す）
    - その他の `Exception` は `logger.exception(operation + " failed")` を記録し
      `HTTPException(500, str(e))` に変換する
    - エンドポイント関数内の明示的な `try/except` で `RuntimeError → HTTPException(400)` などを
      ハンドリングしている場合、その `HTTPException` は本デコレータの第 1 except 節を
      通って素通しされる

    `operation` はログメッセージのプレフィックスに使う（例: `"ocr/run"`）。
    logger はデコレート対象関数のモジュール名から取得するため、各ルーターの既存ロガー設定を
    そのまま継承する。
    """
    def decorator(func):
        logger = get_logger(func.__module__)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except HTTPException:
                raise
            except Exception as e:
                logger.exception("%s failed", operation)
                raise HTTPException(status_code=500, detail=str(e))

        return wrapper

    return decorator
