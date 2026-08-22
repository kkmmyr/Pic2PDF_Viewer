"""Fail-closed validation for sealed lexical-search holdout fixtures."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Set
from typing import Any

PageIdentity = tuple[str, int]


def _require_sha256(value: object, *, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{label} must be a SHA-256 hex digest")
    try:
        bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be a SHA-256 hex digest") from exc
    return value.lower()


def _load_sealed_pages(raw_pages: object) -> dict[PageIdentity, str]:
    if not isinstance(raw_pages, list) or not raw_pages:
        raise ValueError("sealed_corpus.pages must be a non-empty list")
    pages: dict[PageIdentity, str] = {}
    for index, row in enumerate(raw_pages, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"sealed_corpus page {index} must be an object")
        book_name = row.get("book_name")
        page_no = row.get("page_no")
        if not isinstance(book_name, str) or not book_name:
            raise ValueError(f"sealed_corpus page {index} has no book_name")
        if not isinstance(page_no, int) or page_no < 0:
            raise ValueError(f"sealed_corpus page {index} has invalid page_no")
        key = (book_name, page_no)
        if key in pages:
            raise ValueError(f"sealed_corpus has duplicate page: {key}")
        pages[key] = _require_sha256(
            row.get("full_text_sha256"),
            label=f"sealed_corpus page {index} full_text_sha256",
        )
    return pages


def _validate_source_state(conn: sqlite3.Connection, expected_source: str) -> None:
    try:
        state = conn.execute(
            """
            SELECT source_sha256, status
            FROM novel_search_index_state
            WHERE index_name = 'page_icu'
            """
        ).fetchone()
    except sqlite3.OperationalError as exc:
        raise RuntimeError("sealed fixture requires novel_search_index_state") from exc
    if state is None or str(state[1]) != "active" or str(state[0]) != expected_source:
        raise RuntimeError("sealed fixture page ICU source does not match the SQLite snapshot")


def _changed_pages(
    conn: sqlite3.Connection,
    sealed_pages: dict[PageIdentity, str],
) -> list[PageIdentity]:
    changed: list[PageIdentity] = []
    for key, expected_hash in sealed_pages.items():
        rows = conn.execute(
            """
            SELECT COALESCE(p.full_text, '')
            FROM pages p
            JOIN books b ON b.id = p.book_id
            WHERE b.name = ? AND p.page_no = ?
            """,
            key,
        ).fetchall()
        if len(rows) != 1:
            changed.append(key)
            continue
        actual_hash = hashlib.sha256(str(rows[0][0]).encode("utf-8")).hexdigest()
        if actual_hash != expected_hash:
            changed.append(key)
    return changed


def validate_sealed_fixture_corpus(
    conn: sqlite3.Connection,
    metadata: dict[str, Any],
    relevant_pages: Set[PageIdentity],
) -> dict[str, Any]:
    """Validate an optional sealed holdout before building or querying indexes."""
    raw = metadata.get("sealed_corpus")
    if raw is None:
        return {"required": False, "valid": None, "page_count": 0}
    if not isinstance(raw, dict):
        raise ValueError("sealed_corpus must be an object")
    expected_source = _require_sha256(
        raw.get("page_fts_source_sha256"),
        label="sealed_corpus.page_fts_source_sha256",
    )
    sealed_pages = _load_sealed_pages(raw.get("pages"))
    if set(sealed_pages) != relevant_pages:
        raise ValueError("sealed_corpus pages must exactly match all relevant pages")
    _validate_source_state(conn, expected_source)
    mismatches = _changed_pages(conn, sealed_pages)
    if mismatches:
        sample = ", ".join(f"{book} p.{page}" for book, page in mismatches[:3])
        raise RuntimeError(f"sealed fixture page content mismatch: {sample}")
    return {
        "required": True,
        "valid": True,
        "page_count": len(sealed_pages),
        "page_fts_source_sha256": expected_source,
    }
