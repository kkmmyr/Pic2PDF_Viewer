"""C-12: キャラクタ関係グラフ API。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from routers.api_schemas import GraphBookOut, GraphDataResponse
from services.novel_db.connection import with_db
from services.novel_db.graph_query import (
    get_graph_for_series,
    list_books_in_relation_series,
    list_series_with_relations,
)

router = APIRouter()


@router.get("/novel_graph/series")
def get_series_list() -> list[str]:
    """character_relations データが存在するシリーズ一覧を返す。"""
    with with_db() as conn:
        return list_series_with_relations(conn)


@router.get("/novel_graph/series/{series_id}/books", response_model=list[GraphBookOut])
def get_books_in_series(series_id: str) -> list[dict]:
    """シリーズに含まれる書籍一覧を返す（グラフに存在するもの）。"""
    with with_db() as conn:
        return list_books_in_relation_series(conn, series_id)


@router.get("/novel_graph/series/{series_id}/graph", response_model=GraphDataResponse)
def get_graph(series_id: str, book_ids: str | None = None) -> dict:
    """シリーズのグラフデータ（nodes / edges）を返す。

    Query params:
        book_ids: カンマ区切りの book_id リスト（省略時は全冊）
    """
    parsed_book_ids: list[int] | None = None
    if book_ids:
        try:
            parsed_book_ids = [int(x) for x in book_ids.split(",") if x.strip()]
        except ValueError as e:
            raise HTTPException(status_code=400, detail="book_ids must be comma-separated integers") from e

    with with_db() as conn:
        graph = get_graph_for_series(conn, series_id, parsed_book_ids)

    if not graph["nodes"] and not graph["edges"]:
        raise HTTPException(status_code=404, detail=f"No relation data for series: {series_id}")

    return graph
