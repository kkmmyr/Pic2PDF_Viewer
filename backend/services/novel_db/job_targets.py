"""Target resolution for novel database background jobs."""

from __future__ import annotations

from pathlib import Path

import config

from .connection import with_db
from .series_meta import book_names_for_series


def list_all_book_names() -> list[str]:
    images_dir = Path(config.KINDLE_NOVEL_IMAGES_DIR)
    if not images_dir.exists():
        return []
    return sorted(d.name for d in images_dir.iterdir() if d.is_dir())


def list_books_needing_ocr() -> list[str]:
    images_dir = Path(config.KINDLE_NOVEL_IMAGES_DIR)
    if not images_dir.exists():
        return []
    all_dirs = {d.name for d in images_dir.iterdir() if d.is_dir()}
    if not all_dirs:
        return []
    with with_db() as conn:
        rows = conn.execute("SELECT name FROM books WHERE ocr_done_at IS NOT NULL").fetchall()
    done = {r[0] for r in rows}
    return sorted(all_dirs - done)


def list_books_with_ocr_done() -> list[str]:
    with with_db() as conn:
        rows = conn.execute("SELECT name FROM books WHERE ocr_done_at IS NOT NULL ORDER BY name").fetchall()
    return [r[0] for r in rows]


def list_books_needing_full_build() -> list[str]:
    with with_db() as conn:
        rows = conn.execute(
            "SELECT name FROM books WHERE ocr_done_at IS NOT NULL AND indexed_at IS NULL ORDER BY name"
        ).fetchall()
    return [r[0] for r in rows]


def list_books_needing_contexts() -> list[str]:
    with with_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT b.name FROM books b "
            "JOIN pages p ON p.book_id = b.id "
            "JOIN chunks c ON c.page_id = p.id "
            "WHERE b.ocr_done_at IS NOT NULL AND c.contextual_text IS NULL "
            "ORDER BY b.name"
        ).fetchall()
    return [r[0] for r in rows]


def list_books_in_series(series_id: str) -> list[str]:
    images_dir = Path(config.KINDLE_NOVEL_IMAGES_DIR)
    return sorted(book_name for book_name in book_names_for_series(series_id) if (images_dir / book_name).is_dir())


def resolve_targets(job_type: str, target_id: str | None, mode: str) -> list[str]:
    """Resolve a job scope into concrete book directory names."""
    if job_type == "book":
        if not target_id:
            raise ValueError("'book' job requires target_id")
        return [target_id]
    if job_type == "all":
        if mode == "ocr":
            return list_books_needing_ocr()
        if mode == "full_build":
            return list_books_needing_full_build()
        if mode == "generate_contexts":
            return list_books_needing_contexts()
        return list_books_with_ocr_done()
    if job_type == "series":
        if not target_id:
            raise ValueError("'series' job requires target_id (series_id)")
        return list_books_in_series(target_id)
    raise ValueError(f"Unknown job_type: {job_type}")
