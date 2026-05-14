"""search サブモジュール間の共有データクラスとユーティリティ。"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal
from urllib.parse import quote

from services.meta_store import load_meta


ScopeType = Literal["all", "series", "book"]


@dataclass(frozen=True)
class Scope:
    type: ScopeType
    id: str | None = None  # series_id or book_name (`type='all'` のとき None)


@dataclass
class SearchHit:
    book_name: str
    page_no: int
    snippet: str
    has_highlight: bool
    image_url: str | None
    rrf_score: float
    # ページの主要登場人物（character_extractor が生成、未抽出なら空リスト）
    main_characters: list[str] | None = None

    def __post_init__(self) -> None:
        if self.main_characters is None:
            self.main_characters = []


def _image_url(book_name: str, page_no: int) -> str:
    encoded = quote(book_name, safe="")
    return f"/kindle_novel/images/{encoded}/{page_no:03d}.png"


@lru_cache(maxsize=16)
def _resolve_book_names(scope: Scope) -> list[str] | None:
    """scope=all のとき None（全件）、それ以外は対象書籍名のリスト（空なら 0 件）。"""
    if scope.type == "all":
        return None
    if scope.type == "book":
        return [scope.id] if scope.id else []
    if scope.type == "series":
        if not scope.id:
            return []
        meta = load_meta("novel")
        names: list[str] = []
        for key, entry in meta.items():
            if entry.get("series_id") != scope.id:
                continue
            if not key.endswith(".pdf"):
                continue
            names.append(key[: -len(".pdf")])
        return names
    return []


def _fetch_main_characters(
    conn: sqlite3.Connection, keys: list[tuple[str, int]]
) -> dict[tuple[str, int], list[str]]:
    """指定された (book_name, page_no) の組に対して main_characters を一括取得する。"""
    if not keys:
        return {}
    cols = {row[1] for row in conn.execute("PRAGMA table_info(pages)").fetchall()}
    if "main_characters" not in cols:
        return {}
    placeholders = " OR ".join(["(b.name = ? AND p.page_no = ?)"] * len(keys))
    params: list = []
    for book, page in keys:
        params.extend([book, page])
    sql = f"""
        SELECT b.name, p.page_no, p.main_characters
        FROM pages p
        JOIN books b ON p.book_id = b.id
        WHERE {placeholders}
    """
    result: dict[tuple[str, int], list[str]] = {}
    for book_name, page_no, raw in conn.execute(sql, params):
        if raw is None or raw == "":
            result[(book_name, page_no)] = []
        else:
            result[(book_name, page_no)] = [n.strip() for n in raw.split(",") if n.strip()]
    return result
