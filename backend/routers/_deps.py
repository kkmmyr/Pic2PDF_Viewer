"""ルーター共通 FastAPI 依存関数・ヘルパー。"""
from fastapi import HTTPException
from config import VALID_SOURCES
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
