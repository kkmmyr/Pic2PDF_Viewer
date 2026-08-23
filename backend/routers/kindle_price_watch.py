"""Codex ブラウザで観測する Kindle 価格監視 API。"""

from fastapi import APIRouter, HTTPException, Query, status

from routers.schemas.kindle_price_watch import (
    KindlePriceHistoryResponse,
    KindlePriceObservationRequest,
    KindlePriceObservationResponse,
    KindlePriceTargetsResponse,
    KindlePriceWatchCreateRequest,
    KindlePriceWatchDeleteResponse,
    KindlePriceWatchListResponse,
    KindlePriceWatchOut,
    KindlePriceWatchUpdateRequest,
)
from services.kindle_catalog import price_watch

router = APIRouter(prefix="/kindle-price-watches")


def _bad_request(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _not_found(exc: KeyError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc).strip("'"))


@router.get("/targets", response_model=KindlePriceTargetsResponse)
def export_targets():
    """Codex のブラウザ観測処理に渡す有効な URL 一覧。"""
    return {"items": price_watch.export_targets()}


@router.get("", response_model=KindlePriceWatchListResponse)
def list_price_watches():
    return {"items": price_watch.list_watches()}


@router.post("", response_model=KindlePriceWatchOut, status_code=status.HTTP_201_CREATED)
def create_price_watch(request: KindlePriceWatchCreateRequest):
    try:
        return price_watch.create_watch(**request.model_dump())
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.get("/{watch_id}", response_model=KindlePriceWatchOut)
def get_price_watch(watch_id: int):
    try:
        return price_watch.get_watch(watch_id)
    except KeyError as exc:
        raise _not_found(exc) from exc


@router.patch("/{watch_id}", response_model=KindlePriceWatchOut)
def update_price_watch(watch_id: int, request: KindlePriceWatchUpdateRequest):
    try:
        return price_watch.update_watch(watch_id, request.model_dump(exclude_unset=True))
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.delete("/{watch_id}", response_model=KindlePriceWatchDeleteResponse)
def delete_price_watch(watch_id: int):
    try:
        return price_watch.delete_watch(watch_id)
    except KeyError as exc:
        raise _not_found(exc) from exc


@router.get("/{watch_id}/history", response_model=KindlePriceHistoryResponse)
def get_price_history(watch_id: int, limit: int = Query(default=100, ge=1, le=500)):
    try:
        return {"items": price_watch.list_history(watch_id, limit)}
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.post("/{watch_id}/observations", response_model=KindlePriceObservationResponse)
def record_price_observation(watch_id: int, request: KindlePriceObservationRequest):
    try:
        return price_watch.record_observation(watch_id=watch_id, **request.model_dump())
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc
