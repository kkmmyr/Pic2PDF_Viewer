"""Build a read-only, content-addressed OCR text package for isolated Sol jobs."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

INPUT_SCHEMA_VERSION = "sol-input-v1"
SOURCE_HASH_VERSION = "page-no-null-text-record-separator-v1"


def source_sha256(pages: Sequence[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for page in pages:
        digest.update(str(page["page_no"]).encode("ascii"))
        digest.update(b"\x00")
        digest.update(str(page["full_text"]).encode("utf-8"))
        digest.update(b"\x1e")
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.touch(mode=0o600, exist_ok=False)
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_acknowledgement(value: str) -> None:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("privacy acknowledgement must include a timezone")


def export_input_package(
    *,
    database_path: Path,
    book_name: str,
    output_dir: Path,
    privacy_acknowledged_at: str,
    canonical_names: Sequence[str] = (),
    run_id: str | None = None,
    max_input_chars: int = 300_000,
) -> dict[str, Any]:
    _validate_acknowledgement(privacy_acknowledged_at)
    if not book_name.strip():
        raise ValueError("book name is required")
    if max_input_chars <= 0:
        raise ValueError("max_input_chars must be positive")
    normalized_names = [name.strip() for name in canonical_names if name.strip()]
    if len(normalized_names) != len(set(normalized_names)):
        raise ValueError("canonical names must be unique")

    connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        book = connection.execute("SELECT id, name FROM books WHERE name = ?", (book_name,)).fetchone()
        if book is None:
            raise ValueError(f"book not found: {book_name}")
        rows = connection.execute(
            """
            SELECT page_no, full_text
            FROM pages
            WHERE book_id = ? AND index_eligible = 1
            ORDER BY page_no
            """,
            (book["id"],),
        ).fetchall()
    finally:
        connection.close()

    pages: list[dict[str, Any]] = []
    seen_page_numbers: set[int] = set()
    for row in rows:
        page_no = int(row["page_no"])
        full_text = row["full_text"]
        if page_no in seen_page_numbers:
            raise ValueError(f"duplicate page number: {page_no}")
        if not isinstance(full_text, str) or not full_text.strip():
            raise ValueError(f"eligible page {page_no} has no text")
        seen_page_numbers.add(page_no)
        pages.append(
            {
                "page_no": page_no,
                "full_text": full_text,
                "char_count": len(full_text),
            }
        )
    if not pages:
        raise ValueError("book has no index-eligible pages")
    total_chars = sum(page["char_count"] for page in pages)
    if total_chars > max_input_chars:
        raise ValueError(f"input has {total_chars} characters, exceeding limit {max_input_chars}")

    output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    output_dir.chmod(0o700)
    pages_path = output_dir / "pages.jsonl"
    pages_content = "".join(json.dumps(page, ensure_ascii=False, sort_keys=True) + "\n" for page in pages)
    _atomic_write(pages_path, pages_content)
    manifest = {
        "schema_version": INPUT_SCHEMA_VERSION,
        "run_id": run_id or str(uuid.uuid4()),
        "book_name": book_name,
        "source_hash_version": SOURCE_HASH_VERSION,
        "source_sha256": source_sha256(pages),
        "pages_sha256": _file_sha256(pages_path),
        "page_count": len(pages),
        "page_start": pages[0]["page_no"],
        "page_end": pages[-1]["page_no"],
        "total_chars": total_chars,
        "canonical_names": normalized_names,
        "prompt_version": "sol-fact-graph-v1",
        "privacy_acknowledged_at": privacy_acknowledged_at,
        "allowed_outputs": ["facts"],
    }
    _atomic_write(
        output_dir / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return manifest
