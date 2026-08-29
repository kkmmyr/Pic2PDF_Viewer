"""Typed SQLite row conversion for Kindle price watching."""

from __future__ import annotations

from typing import Protocol


class _RowLike(Protocol):
    def __getitem__(self, key: str, /) -> object: ...


def _required_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} is not an integer in the price watch database")
    return value


def _required_float(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} is not numeric in the price watch database")
    return float(value)


def require_lastrowid(value: int | None, message: str) -> int:
    if value is None:
        raise RuntimeError(message)
    return value


def watch_from_row(row: _RowLike) -> dict[str, object]:
    return {
        "id": _required_int(row["id"], "kindle_price_watches.id"),
        "url": row["url"],
        "asin": row["asin"],
        "title": row["title"],
        "threshold_percent": _required_float(
            row["threshold_percent"],
            "kindle_price_watches.threshold_percent",
        ),
        "notify_on_drop": bool(row["notify_on_drop"]),
        "notify_below_threshold": bool(row["notify_below_threshold"]),
        "enabled": bool(row["enabled"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_checked_at": row["last_checked_at"],
        "last_status": row["last_status"],
        "last_error": row["last_error"],
        "last_current_price": row["last_current_price"],
        "last_list_price": row["last_list_price"],
        "last_ratio_percent": row["last_ratio_percent"],
    }


def observation_from_row(row: _RowLike) -> dict[str, object]:
    return {
        "id": _required_int(row["id"], "kindle_price_observations.id"),
        "watch_id": _required_int(row["watch_id"], "kindle_price_observations.watch_id"),
        "observed_at": row["observed_at"],
        "current_price": row["current_price"],
        "list_price": row["list_price"],
        "ratio_percent": row["ratio_percent"],
        "status": row["status"],
        "error_message": row["error_message"],
        "source": row["source"],
    }
