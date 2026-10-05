"""Freeze canonical QA evidence and reject publication after its version changes."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .gpt61_body_publication import current_digest
from .qa_grounding import QaSource
from .search import SearchHit


@dataclass(frozen=True)
class QaSourceSnapshot:
    sources: tuple[QaSource, ...]
    body_versions: dict[str, dict[str, str]]


def freeze_qa_sources(conn: sqlite3.Connection, hits: list[SearchHit]) -> QaSourceSnapshot:
    sources: list[QaSource] = []
    versions: dict[str, dict[str, str]] = {}
    seen: set[tuple[str, int]] = set()
    for hit in hits:
        key = (hit.book_name, hit.page_no)
        if type(hit.page_no) is not int or hit.page_no <= 0 or key in seen:
            raise ValueError("invalid or duplicate QA source page")
        seen.add(key)
        rows = conn.execute(
            "SELECT p.full_text, b.indexed_at FROM pages p JOIN books b ON b.id=p.book_id "
            "WHERE b.name=? AND p.page_no=? AND p.index_eligible=1 AND b.indexed_at IS NOT NULL",
            key,
        ).fetchall()
        if len(rows) != 1 or not isinstance(rows[0][0], str) or not rows[0][0].strip():
            raise ValueError("canonical QA source is unavailable")
        text, indexed_at = rows[0]
        if hit.has_highlight or hit.snippet != text:
            raise ValueError("retrieved QA source differs from canonical body")
        sources.append(QaSource(len(sources), hit.book_name, hit.page_no, text))
        if hit.book_name not in versions:
            versions[hit.book_name] = {
                "body_sha256": current_digest(conn, hit.book_name),
                "indexed_at": str(indexed_at),
            }
    snapshot = QaSourceSnapshot(tuple(sources), versions)
    assert_qa_sources_current(conn, snapshot)
    return snapshot


def assert_qa_sources_current(conn: sqlite3.Connection, snapshot: QaSourceSnapshot) -> None:
    for name, version in snapshot.body_versions.items():
        rows = conn.execute("SELECT indexed_at FROM books WHERE name=?", (name,)).fetchall()
        if (
            len(rows) != 1
            or rows[0][0] is None
            or str(rows[0][0]) != version["indexed_at"]
            or current_digest(conn, name) != version["body_sha256"]
        ):
            raise ValueError("QA body version or RAG availability changed during generation")
    for source in snapshot.sources:
        rows = conn.execute(
            "SELECT p.full_text FROM pages p JOIN books b ON b.id=p.book_id "
            "WHERE b.name=? AND p.page_no=? AND p.index_eligible=1",
            (source.book_name, source.page_no),
        ).fetchall()
        if len(rows) != 1 or rows[0][0] != source.text:
            raise ValueError("canonical QA source changed during generation")
