"""novel_db ハイブリッド検索エンドポイント。"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends

from config import NOVEL_DB_BODY_PAGE_MARGIN, NOVEL_DB_MIN_BODY_CHARS
from routers._deps import log_and_raise_500
from services.novel_db import Scope, hybrid_search, with_db

from ._deps import require_not_locked
from .schemas import SearchRequest

router = APIRouter()


@router.post("/search")
@log_and_raise_500("novel_db/search")
def post_search(
    request: SearchRequest,
    _: None = Depends(require_not_locked),
) -> dict:
    """ハイブリッド検索（[API §7.3]）。

    `min_chars` でノイズページ（章扉・目次・人物紹介・あとがき等）を除外する。
    検索 API では書籍偏りを許容（max_per_book は適用しない）。
    """
    scope = Scope(type=request.scope.type, id=request.scope.id)
    end = request.offset + request.limit
    with with_db() as conn:
        all_hits = hybrid_search(
            conn,
            request.query,
            scope,
            top=end,
            min_chars=NOVEL_DB_MIN_BODY_CHARS,
            body_page_margin=NOVEL_DB_BODY_PAGE_MARGIN,
        )
    page = all_hits[request.offset : end]
    return {
        "hits": [asdict(h) for h in page],
        "total": len(all_hits),
        "offset": request.offset,
        "limit": request.limit,
    }
