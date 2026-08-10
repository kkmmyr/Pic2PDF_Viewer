from __future__ import annotations

from enum import Enum


class PageChangeAction(Enum):
    RETRY_SELECTED = "retry_selected"
    TRY_OPPOSITE = "try_opposite"


def page_change_recovery_actions(
    *,
    page: int,
    retry_limit: int,
) -> tuple[PageChangeAction, ...]:
    """無変化時に許可する操作を、実行順の不変な列として返す。"""
    retries = (PageChangeAction.RETRY_SELECTED,) * max(0, retry_limit)
    if page == 2:
        return (*retries, PageChangeAction.TRY_OPPOSITE)
    return retries


def expected_count_reached(page: int, expected_pages: int | None) -> bool:
    return expected_pages is not None and page >= expected_pages


def capture_stopped_too_early(
    captured_pages: int,
    expected_pages: int | None,
) -> bool:
    return expected_pages is not None and captured_pages < expected_pages
