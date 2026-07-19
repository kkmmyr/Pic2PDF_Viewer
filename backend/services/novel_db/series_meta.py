"""novelメタからシリーズ対象書籍を解決する共通ヘルパー。"""

from __future__ import annotations

from collections.abc import Mapping

from services.meta_store import load_meta


def build_book_series_ids(meta: Mapping[str, Mapping[str, object]]) -> dict[str, str]:
    """`<book>.pdf` キーのメタを `book_name -> series_id` に変換する。"""
    series_ids: dict[str, str] = {}
    for key, entry in meta.items():
        series_id = entry.get("series_id")
        if key.endswith(".pdf") and isinstance(series_id, str) and series_id:
            series_ids[key.removesuffix(".pdf")] = series_id
    return series_ids


def load_book_series_ids() -> dict[str, str]:
    """meta2.dbからnovel書籍のシリーズ索引を1回構築する。"""
    return build_book_series_ids(load_meta("novel"))


def book_names_for_series(series_id: str, series_ids: Mapping[str, str] | None = None) -> set[str]:
    """指定シリーズに属する書籍名集合を返す。"""
    index = series_ids if series_ids is not None else load_book_series_ids()
    return {book_name for book_name, value in index.items() if value == series_id}
