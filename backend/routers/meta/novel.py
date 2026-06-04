"""novel ソース専用のメタデータパッチエンドポイント。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.meta_store import update_meta_locked

router = APIRouter()


class NovelMetaPatchRequest(BaseModel):
    """novel 1 冊のメタを部分更新するリクエスト（4.3）。省略されたフィールドは変更しない。"""
    authors: list[str] | None = None
    series_id: str | None = None
    volume: int | None = None
    volume_clear: bool = False
    publisher: str | None = None
    asin: str | None = None
    isbn: str | None = None
    release_date: str | None = None


@router.patch("/meta/novel/{book_key:path}")
def patch_novel_meta(book_key: str, request: NovelMetaPatchRequest) -> dict:
    """novel ソースの 1 冊メタを部分更新する（4.3）。

    book_key は "{stem}.pdf" 形式。省略フィールドは変更しない。
    """
    all_none = (
        request.authors is None
        and request.series_id is None
        and not request.volume_clear
        and request.volume is None
        and request.publisher is None
        and request.asin is None
        and request.isbn is None
        and request.release_date is None
    )
    if all_none:
        raise HTTPException(status_code=400, detail="No fields to update")

    def _apply(data: dict) -> None:
        entry = dict(data.get(book_key, {}))
        if request.authors is not None:
            cleaned = [a.strip() for a in request.authors if a.strip()]
            entry["authors"] = cleaned
        if request.series_id is not None:
            if request.series_id:
                entry["series_id"] = request.series_id
                entry["series_title"] = request.series_id
            else:
                entry.pop("series_id", None)
                entry.pop("series_title", None)
        if request.volume_clear:
            entry.pop("volume", None)
        elif request.volume is not None:
            entry["volume"] = request.volume
        for field in ("publisher", "asin", "isbn", "release_date"):
            val = getattr(request, field)
            if val is not None:
                if val:
                    entry[field] = val
                else:
                    entry.pop(field, None)
        data[book_key] = entry

    update_meta_locked("novel", _apply)
    return {"message": "Updated"}
