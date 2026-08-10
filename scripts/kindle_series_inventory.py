from __future__ import annotations

import re

from kindle_series_models import (
    DEFAULT_SERIES,
    LABEL_SOURCES,
    SeriesBook,
    SeriesCaptureError,
)


def _source_from_title(title: str) -> str:
    matches = [source for label, source in LABEL_SOURCES.items() if label in title]
    if len(matches) != 1:
        raise SeriesCaptureError(f"Cannot safely classify Kindle source: {title}")
    return matches[0]


def _japanese_number(value: str) -> int | None:
    digits = {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if value in digits:
        return digits[value]
    if value == "十":
        return 10
    if "十" in value:
        tens, ones = value.split("十", 1)
        if tens not in {"", *digits} or ones not in {"", *digits}:
            return None
        return digits.get(tens, 1) * 10 + digits.get(ones, 0)
    return None


def _volume_from_title(title: str, *, series_name: str, source: str) -> float | None:
    if source == "comic":
        match = re.search(r"[ 　](\d+)[ 　]*\(プリンセス・コミックス\)$", title)
        return float(match.group(1)) if match else None
    match = re.match(
        rf"^{re.escape(series_name)}[ 　]+([一二三四五六七八九十]+)(?:[ 　]|$)",
        title,
    )
    if match:
        number = _japanese_number(match.group(1))
        return float(number) if number is not None else None
    if series_name == DEFAULT_SERIES and title.startswith(f"{series_name}　"):
        return 1.0
    return None


def _validate_capture_state(asin: str, capture_state: str) -> None:
    if capture_state not in {
        "not_captured",
        "captured",
        "capture_pending",
        "multiple_links",
    }:
        raise SeriesCaptureError(f"Unknown capture state for {asin}: {capture_state}")


def _inventory_book(item: dict, *, series_name: str) -> SeriesBook:
    title = str(item.get("title") or "")
    asin = str(item.get("asin") or "")
    if item.get("ownership") != "purchased":
        raise SeriesCaptureError(f"Series item is not a purchased book: {asin} {title}")
    source = _source_from_title(title)
    volume_number = item.get("volume_number")
    if not isinstance(volume_number, (int, float)):
        volume_number = _volume_from_title(
            title,
            series_name=series_name,
            source=source,
        )
    if volume_number is None:
        raise SeriesCaptureError(
            f"Cannot safely determine volume number: {asin} {title}"
        )
    capture_state = str(item.get("capture_state") or "")
    _validate_capture_state(asin, capture_state)
    return SeriesBook(
        asin=asin,
        title=title,
        source=source,
        volume_number=float(volume_number),
        capture_state=capture_state,
    )


def build_inventory(
    items: list[dict],
    *,
    series_name: str,
    expected_total: int | None,
) -> list[SeriesBook]:
    books: list[SeriesBook] = []
    seen_asins: set[str] = set()
    for item in items:
        title = str(item.get("title") or "")
        catalog_series = str(item.get("series_name") or "")
        if series_name not in title and catalog_series != series_name:
            continue
        asin = str(item.get("asin") or "")
        if not asin or asin in seen_asins:
            raise SeriesCaptureError(
                f"Missing or duplicate ASIN in series inventory: {asin}"
            )
        books.append(_inventory_book(item, series_name=series_name))
        seen_asins.add(asin)

    books.sort(key=lambda book: book.sort_key)
    if expected_total is not None and len(books) != expected_total:
        raise SeriesCaptureError(
            f"Expected {expected_total} series books, but catalog returned {len(books)}"
        )
    if not books:
        raise SeriesCaptureError(f"No purchased books found for series: {series_name}")
    return books
