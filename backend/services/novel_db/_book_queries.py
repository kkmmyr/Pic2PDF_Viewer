"""novel.db / images_dir を参照する書籍一覧クエリ群。

job_worker.py が再構築対象書籍を絞り込むために使用する純粋なクエリ関数をまとめる。
"""
from __future__ import annotations

from pathlib import Path

from config import KINDLE_NOVEL_IMAGES_DIR

from .connection import with_db


def _list_all_book_names() -> list[str]:
    """images/ 配下のサブディレクトリ名を書籍 stem として返す。"""
    images_dir = Path(KINDLE_NOVEL_IMAGES_DIR)
    if not images_dir.exists():
        return []
    return sorted(d.name for d in images_dir.iterdir() if d.is_dir())


def _list_books_needing_ocr() -> list[str]:
    """OCR 未完了の書籍ディレクトリ一覧（images_dir に存在 かつ ocr_done_at 未設定）。"""
    images_dir = Path(KINDLE_NOVEL_IMAGES_DIR)
    if not images_dir.exists():
        return []
    all_dirs = {d.name for d in images_dir.iterdir() if d.is_dir()}
    if not all_dirs:
        return []
    with with_db() as conn:
        rows = conn.execute(
            "SELECT name FROM books WHERE ocr_done_at IS NOT NULL"
        ).fetchall()
    done = {r[0] for r in rows}
    return sorted(all_dirs - done)


def _list_books_with_ocr_done() -> list[str]:
    """OCR 完了済みの書籍名一覧を novel.db の books テーブルから返す。"""
    with with_db() as conn:
        rows = conn.execute(
            "SELECT name FROM books WHERE ocr_done_at IS NOT NULL ORDER BY name"
        ).fetchall()
    return [r[0] for r in rows]


def _list_books_needing_full_build() -> list[str]:
    """Full Build 未完了の書籍名一覧（OCR 済み & indexed_at 未設定）。"""
    with with_db() as conn:
        rows = conn.execute(
            "SELECT name FROM books "
            "WHERE ocr_done_at IS NOT NULL AND indexed_at IS NULL ORDER BY name"
        ).fetchall()
    return [r[0] for r in rows]


def _list_books_needing_contexts() -> list[str]:
    """contextual_text が未設定のチャンクを持つ書籍名一覧。"""
    with with_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT b.name FROM books b "
            "JOIN pages p ON p.book_id = b.id "
            "JOIN chunks c ON c.page_id = p.id "
            "WHERE b.ocr_done_at IS NOT NULL AND c.contextual_text IS NULL "
            "ORDER BY b.name"
        ).fetchall()
    return [r[0] for r in rows]


def _get_series_id(book_name: str) -> str | None:
    """meta.json から書籍 stem に対応する series_id を返す。なければ None。"""
    from services.meta_store import load_meta
    meta = load_meta("novel")
    key = f"{book_name}.pdf"
    entry = meta.get(key, {})
    return entry.get("series_id") or None


def _list_books_in_series(series_id: str) -> list[str]:
    """meta.json から指定 series_id に属する novel 書籍の stem 一覧を返す。"""
    from services.meta_store import load_meta
    images_dir = Path(KINDLE_NOVEL_IMAGES_DIR)
    meta = load_meta("novel")
    names: list[str] = []
    for key, entry in meta.items():
        if entry.get("series_id") != series_id:
            continue
        if not key.endswith(".pdf"):
            continue
        stem = key[: -len(".pdf")]
        if (images_dir / stem).is_dir():
            names.append(stem)
    return sorted(names)
