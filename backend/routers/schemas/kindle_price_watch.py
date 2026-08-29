"""Kindle 価格監視 API の入出力スキーマ。"""

from typing import Literal

from pydantic import BaseModel, Field

PriceStatus = Literal["ok", "partial", "failed"]


class KindlePriceWatchCreateRequest(BaseModel):
    url: str = Field(min_length=1, max_length=1000)
    title: str | None = Field(default=None, max_length=500)
    threshold_percent: float = Field(default=50.0, ge=1, le=100)
    notify_on_drop: bool = True
    notify_below_threshold: bool = True
    enabled: bool = True


class KindlePriceWatchUpdateRequest(BaseModel):
    url: str | None = Field(default=None, min_length=1, max_length=1000)
    title: str | None = Field(default=None, max_length=500)
    threshold_percent: float | None = Field(default=None, ge=1, le=100)
    notify_on_drop: bool | None = None
    notify_below_threshold: bool | None = None
    enabled: bool | None = None


class KindlePriceObservationRequest(BaseModel):
    current_price: int | None = Field(default=None, ge=0)
    list_price: int | None = Field(default=None, ge=0)
    status: PriceStatus | None = None
    error_message: str | None = Field(default=None, max_length=1000)
    source: Literal["codex_browser", "manual"] = "codex_browser"
    title: str | None = Field(default=None, max_length=500)


class KindlePriceObservationOut(BaseModel):
    id: int
    watch_id: int
    observed_at: str
    current_price: int | None
    list_price: int | None
    ratio_percent: float | None
    status: PriceStatus
    error_message: str | None
    source: Literal["codex_browser", "manual"]


class KindlePriceWatchOut(BaseModel):
    id: int
    url: str
    asin: str
    title: str | None
    threshold_percent: float
    notify_on_drop: bool
    notify_below_threshold: bool
    enabled: bool
    created_at: str
    updated_at: str
    last_checked_at: str | None
    last_status: Literal["never", "ok", "partial", "failed"]
    last_error: str | None
    last_current_price: int | None
    last_list_price: int | None
    last_ratio_percent: float | None


class KindlePriceWatchListResponse(BaseModel):
    items: list[KindlePriceWatchOut]


class KindlePriceTargetOut(BaseModel):
    id: int
    url: str
    asin: str
    title: str | None
    threshold_percent: float


class KindlePriceTargetsResponse(BaseModel):
    items: list[KindlePriceTargetOut]


class KindlePriceHistoryResponse(BaseModel):
    items: list[KindlePriceObservationOut]


class KindlePriceNotificationOut(BaseModel):
    kind: Literal["price_drop", "below_threshold"]
    sent: bool


class KindlePriceObservationResponse(BaseModel):
    observation: KindlePriceObservationOut
    price_dropped: bool
    below_threshold: bool
    notifications: list[KindlePriceNotificationOut]


class KindlePriceWatchDeleteResponse(BaseModel):
    id: int
    deleted: bool
