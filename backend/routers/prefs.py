"""UI プリファレンス（フィルター / ピン）ルーター。

エンドポイント（§12）:
  GET    /api/prefs              ?source= → フィルター + ピン全件
  PATCH  /api/prefs/filters      body: {source, read_state_filter?, genre_filter?}
  PUT    /api/prefs/pins         body: {source, pin_type, group_id, book_name}
  DELETE /api/prefs/pins         ?source=&pin_type=&group_id=
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routers._deps import assert_valid_source, validated_source
from services.prefs_store import delete_pin, get_prefs, set_pin, update_filters

router = APIRouter()

_VALID_PIN_TYPES = frozenset({"series", "author"})


class UpdateFiltersRequest(BaseModel):
    source: str
    read_state_filter: str | None = None
    genre_filter: str | None = None


class SetPinRequest(BaseModel):
    source: str
    pin_type: str
    group_id: str
    book_name: str


@router.get("/prefs")
def get_prefs_endpoint(source: str = Depends(validated_source)) -> dict:
    """指定ソースのフィルター設定とピン情報を返す。"""
    return get_prefs(source)


@router.patch("/prefs/filters")
def patch_filters(request: UpdateFiltersRequest) -> dict:
    """readStateFilter / genreFilter を部分更新する。"""
    assert_valid_source(request.source)
    if request.read_state_filter is None and request.genre_filter is None:
        raise HTTPException(
            status_code=400,
            detail="read_state_filter or genre_filter must be specified",
        )
    update_filters(
        request.source,
        read_state_filter=request.read_state_filter,
        genre_filter=request.genre_filter,
    )
    return {"message": "Updated"}


@router.put("/prefs/pins")
def put_pin(request: SetPinRequest) -> dict:
    """グループピンを登録または上書きする。"""
    assert_valid_source(request.source)
    if request.pin_type not in _VALID_PIN_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"pin_type must be one of: {', '.join(sorted(_VALID_PIN_TYPES))}",
        )
    set_pin(request.source, request.pin_type, request.group_id, request.book_name)
    return {"message": "Pinned"}


@router.delete("/prefs/pins")
def remove_pin(source: str, pin_type: str, group_id: str) -> dict:
    """グループピンを削除する。"""
    assert_valid_source(source)
    if pin_type not in _VALID_PIN_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"pin_type must be one of: {', '.join(sorted(_VALID_PIN_TYPES))}",
        )
    delete_pin(source, pin_type, group_id)
    return {"message": "Unpinned"}
