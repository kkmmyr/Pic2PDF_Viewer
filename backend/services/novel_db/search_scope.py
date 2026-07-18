"""検索対象スコープと書籍名解決。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from services.meta_store import load_meta

ScopeType = Literal["all", "series", "book"]


@dataclass(frozen=True)
class Scope:
    type: ScopeType
    id: str | None = None


@lru_cache(maxsize=16)
def resolve_book_names(scope: Scope) -> list[str] | None:
    """scope=all は None、それ以外は対象書籍名を返す。"""
    if scope.type == "all":
        return None
    if scope.type == "book":
        return [scope.id] if scope.id else []
    if scope.type == "series":
        if not scope.id:
            return []
        return [
            key[: -len(".pdf")]
            for key, entry in load_meta("novel").items()
            if entry.get("series_id") == scope.id and key.endswith(".pdf")
        ]
    return []
