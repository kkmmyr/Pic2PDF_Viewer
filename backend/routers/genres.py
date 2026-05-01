"""
ジャンルリスト管理ルーター。

GET  /api/genres        - ソース別ジャンルリストを返す
POST /api/genres        - ジャンルを追加する
DELETE /api/genres/{name} - ジャンルをリストから削除する
PATCH /api/genres/reorder - 表示順を更新する
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routers._deps import validated_source, assert_valid_source
from services.genre_store import load_genres, save_genres

router = APIRouter()


class AddGenreRequest(BaseModel):
    source: str = "generated"
    name: str


class ReorderGenresRequest(BaseModel):
    source: str = "generated"
    genres: list[str]


@router.get("/genres")
def get_genres(source: str = Depends(validated_source)) -> list[str]:
    return load_genres(source)


@router.post("/genres")
def add_genre(request: AddGenreRequest) -> dict:
    assert_valid_source(request.source)
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Genre name cannot be empty")
    genres = load_genres(request.source)
    if name in genres:
        raise HTTPException(status_code=409, detail="Genre already exists")
    genres.append(name)
    save_genres(request.source, genres)
    return {"genres": genres}


@router.delete("/genres/{name}")
def delete_genre(name: str, source: str = Depends(validated_source)) -> dict:
    genres = load_genres(source)
    if name not in genres:
        raise HTTPException(status_code=404, detail="Genre not found")
    genres = [g for g in genres if g != name]
    save_genres(source, genres)
    return {"genres": genres}


@router.patch("/genres/reorder")
def reorder_genres(request: ReorderGenresRequest) -> dict:
    assert_valid_source(request.source)
    existing = set(load_genres(request.source))
    if set(request.genres) != existing:
        raise HTTPException(status_code=400, detail="Genre list mismatch")
    save_genres(request.source, request.genres)
    return {"genres": request.genres}
