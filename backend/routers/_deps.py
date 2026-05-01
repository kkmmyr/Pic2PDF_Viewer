"""ルーター共通 FastAPI 依存関数・ヘルパー。"""
from fastapi import HTTPException
from config import VALID_SOURCES


def validated_source(source: str = "generated") -> str:
    """クエリパラメーター `source` を検証して返す。無効値なら 400 を返す。"""
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail="Invalid source")
    return source


def assert_valid_source(source: str) -> None:
    """リクエストボディの `source` フィールドを検証する。無効値なら 400 を発生させる。"""
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail="Invalid source")
