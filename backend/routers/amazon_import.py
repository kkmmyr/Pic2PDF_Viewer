"""Amazon CSV 固定パスインポート。

POST /api/amazon/import?source=novel|comic
"""

from fastapi import APIRouter, HTTPException

from routers.api_schemas import AmazonImportResponse
from services.amazon_csv_importer import ImportResult, run_import

router = APIRouter()


@router.post("/amazon/import", response_model=AmazonImportResponse)
def amazon_csv_import(source: str = "novel") -> dict:
    """固定パスの Amazon CSV から meta.json を著者/ASIN で補完する。

    Returns:
        {"updated": int, "skipped": int, "unmatched": int}
    """
    if source not in ("novel", "comic"):
        raise HTTPException(status_code=400, detail=f"source は 'novel' または 'comic' を指定してください: {source!r}")

    try:
        result: ImportResult = run_import(source)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return {
        "updated": result.updated,
        "skipped": result.skipped,
        "unmatched": result.unmatched,
    }
