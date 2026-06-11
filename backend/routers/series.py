"""シリーズ手動編集ルーター。

`POST /api/series/assign` / `POST /api/series/unassign` / `POST /api/series/reorder`。
`POST /api/series/suggest` で既存シリーズへの紐付け候補を提案（A-1、書き込みなし）。
シリーズ自動グループ化は撤去済み（2026-05-09、Phase 6）。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from routers._deps import assert_valid_source, validate_request_targets
from services.meta_store import MetaDict, load_meta, make_key, update_meta_locked
from services.series_detector import stable_series_id
from services.series_suggester import suggest_series

router = APIRouter()


# ---------------------------------------------------------------------------
# 手動編集 API
# ---------------------------------------------------------------------------


class AssignSeriesRequest(BaseModel):
    """書籍を既存または新規シリーズに割り当てるリクエスト。

    `index` は単一の float、または `names` と同じ長さの float 配列（各書籍に
    個別の巻数を割り当てたい一括登録ケース）を受け付ける。
    """

    path: str = ""
    names: list[str]
    title: str
    index: float | list[float]
    id: str | None = None  # 省略時はバックエンドで生成
    source: str = "doujin"


class UnassignSeriesRequest(BaseModel):
    """書籍をシリーズから外すリクエスト。"""

    path: str = ""
    names: list[str]
    source: str = "doujin"


class ReorderSeriesRequest(BaseModel):
    """同じシリーズに属する書籍の `series_index` を `names` の順序で振り直すリクエスト。"""

    path: str = ""
    names: list[str]
    series_id: str
    source: str = "doujin"


@router.post("/series/assign")
def assign_series(request: AssignSeriesRequest) -> dict:
    """書籍を既存または新規シリーズに割り当てる（手動編集）。

    `index` が float なら全 names に同じ巻数、配列なら names[i] に index[i] を
    割り当てる（複数選択からの一括登録用）。
    """
    assert_valid_source(request.source)
    if not request.title.strip():
        raise HTTPException(status_code=400, detail="title must not be empty")
    if not request.names:
        raise HTTPException(status_code=400, detail="names must not be empty")

    # index を names と同じ長さの float リストに正規化
    if isinstance(request.index, list):
        if len(request.index) != len(request.names):
            raise HTTPException(
                status_code=400,
                detail="index list must have the same length as names",
            )
        indexes = [float(v) for v in request.index]
    else:
        indexes = [float(request.index)] * len(request.names)

    validate_request_targets(request.path, request.names)

    # id 省略時は title と「対象書籍のうち最初の書籍の作者集合」から生成
    series_id = request.id

    def _apply(data: MetaDict) -> None:
        nonlocal series_id
        if series_id is None:
            # 最初の書籍の authors を見て id を生成（同じ title + 同じ作者なら同じ id になる）
            first_key = make_key(request.path, request.names[0])
            first_authors = data.get(first_key, {}).get("authors") or []
            authors_key = tuple(sorted({a.strip() for a in first_authors if a.strip()}))
            series_id = stable_series_id(request.title.strip(), authors_key)

        for name, idx in zip(request.names, indexes, strict=True):
            key = make_key(request.path, name)
            existing = dict(data.get(key, {}))
            existing["series_id"] = series_id
            existing["series_title"] = request.title.strip()
            existing["series_index"] = idx
            data[key] = existing  # type: ignore[assignment]

    update_meta_locked(request.source, _apply)
    return {"message": "Assigned", "id": series_id, "updated_count": len(request.names)}


@router.post("/series/unassign")
def unassign_series(request: UnassignSeriesRequest) -> dict:
    """書籍をシリーズから外す（series_* フィールドを削除）。"""
    assert_valid_source(request.source)
    if not request.names:
        raise HTTPException(status_code=400, detail="names must not be empty")

    validate_request_targets(request.path, request.names)

    def _apply(data: MetaDict) -> None:
        for name in request.names:
            key = make_key(request.path, name)
            existing = data.get(key)
            if not existing:
                continue
            existing.pop("series_id", None)
            existing.pop("series_title", None)
            existing.pop("series_index", None)

    update_meta_locked(request.source, _apply)
    return {"message": "Unassigned", "updated_count": len(request.names)}


@router.post("/series/reorder")
def reorder_series(request: ReorderSeriesRequest) -> dict:
    """シリーズ内の `series_index` を `names` の順序で 1.0, 2.0, 3.0, ... に振り直す（DnD 並べ替え）。

    `names` には対象シリーズに属する書籍を **新しい順序で** 渡す。`series_id` が
    一致しない書籍が混じっていれば 400。他のメタフィールドは保持する。
    """
    assert_valid_source(request.source)
    if not request.names:
        raise HTTPException(status_code=400, detail="names must not be empty")
    if not request.series_id.strip():
        raise HTTPException(status_code=400, detail="series_id must not be empty")

    validate_request_targets(request.path, request.names)

    def _apply(data: MetaDict) -> None:
        # 全書籍が対象シリーズに属することを先に検査（一部だけ更新して中途半端な状態に
        # ならないように）。
        for name in request.names:
            key = make_key(request.path, name)
            entry = data.get(key)
            if not entry or entry.get("series_id") != request.series_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"'{name}' does not belong to series '{request.series_id}'",
                )

        for i, name in enumerate(request.names):
            key = make_key(request.path, name)
            existing = dict(data[key])
            existing["series_index"] = float(i + 1)
            data[key] = existing  # type: ignore[assignment]

    update_meta_locked(request.source, _apply)
    return {"message": "Reordered", "updated_count": len(request.names)}


# ---------------------------------------------------------------------------
# AI 提案 API（A-1）
# ---------------------------------------------------------------------------


class SuggestSeriesRequest(BaseModel):
    """選択された書籍に対する既存シリーズの紐付け候補を取得するリクエスト。"""

    path: str = ""
    names: list[str]
    source: str = "doujin"


@router.post("/series/suggest")
def suggest_series_endpoint(request: SuggestSeriesRequest) -> dict:
    """選択書籍に対する既存シリーズへの紐付け候補を返す（A-1、書き込みなし）。

    `services.series_suggester.suggest_series` のラッパー。
    """
    assert_valid_source(request.source)
    if not request.names:
        raise HTTPException(status_code=400, detail="names must not be empty")

    validate_request_targets(request.path, request.names)

    meta = load_meta(request.source)
    candidates = suggest_series(meta, request.path, request.names)
    return {"candidates": candidates}
