"""novel タブ向けの書籍一覧 / シリーズ一覧の取得。

novel.db の DB 状態と既存 meta.json（authors / series_id / series_title）を結合する。
詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §9。
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from config import KINDLE_NOVEL_IMAGES_DIR
from services.meta_store import load_meta


@dataclass
class BookSummary:
    name: str
    authors: list[str]
    series_id: str | None
    series_title: str | None
    is_indexed: bool
    page_count: int | None
    indexed_at: str | None
    thumbnail_url: str | None
    ocr_done_at: str | None = None
    volume: int | None = None
    publisher: str | None = None
    asin: str | None = None


@dataclass
class SeriesSummary:
    id: str
    name: str
    book_count: int


def _meta_key(book_name: str) -> str:
    """書籍 stem (= books.name) を meta.json のキー (= "{stem}.pdf") に変換する。"""
    return f"{book_name}.pdf"


def _thumbnail_url(book_name: str) -> str:
    """先頭画像 (`001.png`) を縮小表示用の URL として返す。事前生成しない。"""
    encoded = quote(book_name, safe="")
    return f"/kindle_novel/images/{encoded}/001.png"


def _fetch_indexed_status(conn: sqlite3.Connection) -> dict[str, dict]:
    """novel.db から書籍の {name: {page_count, indexed_at, ocr_done_at}} を返す。"""
    rows = conn.execute(
        "SELECT name, page_count, indexed_at, ocr_done_at FROM books"
    ).fetchall()
    return {
        name: {
            "page_count": page_count,
            "indexed_at": indexed_at,
            "ocr_done_at": ocr_done_at,
        }
        for name, page_count, indexed_at, ocr_done_at in rows
    }


def list_books(conn: sqlite3.Connection) -> list[BookSummary]:
    """novel ソースの全書籍を返す（`images/` のサブディレクトリを起点）。"""
    images_dir = Path(KINDLE_NOVEL_IMAGES_DIR)
    if not images_dir.exists():
        return []

    meta = load_meta("novel")
    indexed = _fetch_indexed_status(conn)

    summaries: list[BookSummary] = []
    for book_dir in sorted(d for d in images_dir.iterdir() if d.is_dir()):
        name = book_dir.name
        meta_entry = meta.get(_meta_key(name), {})
        info = indexed.get(name)
        summaries.append(
            BookSummary(
                name=name,
                authors=list(meta_entry.get("authors", [])),
                series_id=meta_entry.get("series_id"),
                series_title=meta_entry.get("series_title"),
                is_indexed=info is not None,
                page_count=info["page_count"] if info else None,
                indexed_at=info["indexed_at"] if info else None,
                thumbnail_url=_thumbnail_url(name),
                ocr_done_at=info["ocr_done_at"] if info else None,
                volume=meta_entry.get("volume"),
                publisher=meta_entry.get("publisher"),
                asin=meta_entry.get("asin"),
            )
        )
    return summaries


def list_series(conn: sqlite3.Connection) -> list[SeriesSummary]:
    """novel ソースのシリーズ一覧を返す（書籍 1 件以上のもののみ）。

    シリーズ未所属書籍は本一覧（list_books）から取得し、シリーズスコープ
    の選択肢には含めない（要件 TBD-7）。
    """
    books = list_books(conn)
    by_id: dict[str, dict] = {}
    for b in books:
        if not b.series_id or not b.series_title:
            continue
        entry = by_id.setdefault(
            b.series_id, {"name": b.series_title, "count": 0}
        )
        entry["count"] += 1
        # 同一 series_id で title が複数あった場合は最頻値を採用する保険
        # （通常起きないが、meta.json 編集ミスへの耐性）
    # title 不一致を統合
    title_counts: dict[str, Counter] = {}
    for b in books:
        if b.series_id and b.series_title:
            title_counts.setdefault(b.series_id, Counter())[b.series_title] += 1

    return [
        SeriesSummary(
            id=sid,
            name=title_counts[sid].most_common(1)[0][0] if sid in title_counts else by_id[sid]["name"],
            book_count=by_id[sid]["count"],
        )
        for sid in sorted(by_id.keys())
    ]
