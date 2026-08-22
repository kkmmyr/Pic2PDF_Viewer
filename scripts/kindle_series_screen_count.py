from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from statistics import median
from typing import Any

from kindle_series_models import SeriesBook, SeriesCaptureError

POLICY_VERSION = "kindle-series-screen-count-v1"
_MIN_REFERENCE_COUNT = 3
_LOW_RATIO = 0.5
_HIGH_RATIO = 2.0
_WARNING_FIELDS = frozenset(
    {
        "code",
        "severity",
        "policy_version",
        "asin",
        "source",
        "captured_screens",
        "reference_count",
        "reference_min",
        "reference_median",
        "reference_max",
        "ratio_to_median",
    }
)


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _latest_history_counts(
    books: list[SeriesBook],
    jobs: list[dict],
) -> dict[str, tuple[str, int]]:
    captured = {book.asin: book for book in books if book.capture_state == "captured"}
    latest: dict[str, tuple[tuple[str, int], str, int]] = {}
    for position, job in enumerate(jobs):
        asin = str(job.get("asin") or "")
        book = captured.get(asin)
        screen_count = _positive_int(job.get("captured_screens"))
        if (
            book is None
            or job.get("status") != "succeeded"
            or job.get("source") != book.source
            or screen_count is None
        ):
            continue
        timestamp = str(job.get("completed_at") or job.get("requested_at") or "")
        order = (timestamp, -position)
        previous = latest.get(asin)
        if previous is None or order > previous[0]:
            latest[asin] = (order, book.source, screen_count)
    return {asin: (source, count) for asin, (_order, source, count) in latest.items()}


def _reference_counts(
    books: list[SeriesBook],
    jobs: list[dict],
    session_counts: Mapping[str, int],
) -> dict[str, dict[str, int]]:
    by_source: dict[str, dict[str, int]] = {"comic": {}, "novel": {}}
    for asin, (source, count) in _latest_history_counts(books, jobs).items():
        by_source[source][asin] = count
    book_by_asin = {book.asin: book for book in books}
    for asin, value in session_counts.items():
        book = book_by_asin.get(asin)
        count = _positive_int(value)
        if book is not None and count is not None:
            by_source[book.source][asin] = count
    return by_source


def _warning(
    book: SeriesBook,
    captured_screens: int,
    references: list[int],
) -> dict[str, Any] | None:
    if len(references) < _MIN_REFERENCE_COUNT:
        return None
    reference_median = float(median(references))
    ratio = captured_screens / reference_median
    if _LOW_RATIO <= ratio <= _HIGH_RATIO:
        return None
    return {
        "code": "series_screen_count_outlier_candidate",
        "severity": "warning",
        "policy_version": POLICY_VERSION,
        "asin": book.asin,
        "source": book.source,
        "captured_screens": captured_screens,
        "reference_count": len(references),
        "reference_min": min(references),
        "reference_median": reference_median,
        "reference_max": max(references),
        "ratio_to_median": round(ratio, 6),
    }


@dataclass
class SeriesScreenCountPolicy:
    counts_by_source: dict[str, dict[str, int]]

    @classmethod
    def from_history(
        cls,
        books: list[SeriesBook],
        jobs: list[dict],
        session_counts: Mapping[str, int],
    ) -> SeriesScreenCountPolicy:
        return cls(_reference_counts(books, jobs, session_counts))

    def observe(
        self,
        book: SeriesBook,
        captured_screens: Any,
    ) -> dict[str, Any] | None:
        count = _positive_int(captured_screens)
        if count is None:
            raise SeriesCaptureError(
                f"Succeeded capture has invalid captured_screens: {book.asin}"
            )
        source_counts = self.counts_by_source.setdefault(book.source, {})
        references = [
            value for asin, value in source_counts.items() if asin != book.asin
        ]
        warning = _warning(book, count, references)
        source_counts[book.asin] = count
        return warning


def normalize_screen_count_warning(
    value: Any,
    *,
    allowed_asins: set[str],
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _WARNING_FIELDS:
        raise SeriesCaptureError("Session screen-count warning is invalid")
    asin = value.get("asin")
    source = value.get("source")
    integer_fields = (
        "captured_screens",
        "reference_count",
        "reference_min",
        "reference_max",
    )
    integers = {field: _positive_int(value.get(field)) for field in integer_fields}
    reference_median = value.get("reference_median")
    ratio = value.get("ratio_to_median")
    if (
        value.get("code") != "series_screen_count_outlier_candidate"
        or value.get("severity") != "warning"
        or value.get("policy_version") != POLICY_VERSION
        or not isinstance(asin, str)
        or asin not in allowed_asins
        or source not in {"comic", "novel"}
        or any(item is None for item in integers.values())
        or integers["reference_count"] < _MIN_REFERENCE_COUNT
        or isinstance(reference_median, bool)
        or not isinstance(reference_median, (int, float))
        or reference_median <= 0
        or isinstance(ratio, bool)
        or not isinstance(ratio, (int, float))
        or ratio <= 0
    ):
        raise SeriesCaptureError("Session screen-count warning is invalid")
    captured_screens = integers["captured_screens"]
    reference_min = integers["reference_min"]
    reference_max = integers["reference_max"]
    assert captured_screens is not None
    assert reference_min is not None
    assert reference_max is not None
    if (
        not reference_min <= reference_median <= reference_max
        or round(captured_screens / reference_median, 6) != ratio
        or _LOW_RATIO <= ratio <= _HIGH_RATIO
    ):
        raise SeriesCaptureError("Session screen-count warning is inconsistent")
    return dict(value)
