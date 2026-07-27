"""novel_db ルーター専用 FastAPI 依存関数。"""

from typing import Annotated

from fastapi import Depends, HTTPException, Path

from services.novel_db.job_queue import job_queue
from utils.path_utils import validate_safe_name


def require_not_locked() -> None:
    """再構築ジョブ実行中なら 503 を返す共通チェック。Depends() で注入する。"""
    if job_queue.is_running:
        raise HTTPException(
            status_code=503,
            detail="rebuild is in progress",
            headers={"Retry-After": "10"},
        )


def validated_book_name(book_name: Annotated[str, Path()]) -> str:
    """URL から受け取った書籍名を単一ディレクトリ名として検証する。"""
    return validate_safe_name(book_name, param_name="book_name")


ValidatedBookName = Annotated[str, Depends(validated_book_name)]
