"""生成済み要約・人物説明のsnapshot codec。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SNAPSHOT_SCHEMA_VERSION = 2
_SUPPORTED_SNAPSHOT_SCHEMAS = {1, SNAPSHOT_SCHEMA_VERSION}


@dataclass(frozen=True)
class CharacterSnapshot:
    name: str
    summary: str | None
    first_page: int
    page_count: int
    generated_at: str | None


@dataclass(frozen=True)
class GeneratedContentSnapshot:
    schema_version: int
    captured_at: str
    book_name: str
    summary: str | None
    summary_generated_at: str | None
    catalog_summary: str | None
    catalog_summary_generated_at: str | None
    characters: tuple[CharacterSnapshot, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def capture_generated_content(
    conn: sqlite3.Connection,
    book_name: str,
    *,
    captured_at: str | None = None,
) -> GeneratedContentSnapshot:
    book = conn.execute(
        """
        SELECT id, name, summary, summary_generated_at,
               catalog_summary, catalog_summary_generated_at
        FROM books WHERE name = ?
        """,
        (book_name,),
    ).fetchone()
    if book is None:
        raise ValueError(f"book not found: {book_name}")
    rows = conn.execute(
        """
        SELECT name, summary, first_page, page_count, generated_at
        FROM book_characters WHERE book_id = ? ORDER BY name
        """,
        (book["id"],),
    ).fetchall()
    characters = tuple(
        CharacterSnapshot(
            name=str(row["name"]),
            summary=row["summary"],
            first_page=int(row["first_page"]),
            page_count=int(row["page_count"]),
            generated_at=row["generated_at"],
        )
        for row in rows
    )
    return GeneratedContentSnapshot(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        captured_at=captured_at or datetime.now(UTC).isoformat(),
        book_name=str(book["name"]),
        summary=book["summary"],
        summary_generated_at=book["summary_generated_at"],
        catalog_summary=book["catalog_summary"],
        catalog_summary_generated_at=book["catalog_summary_generated_at"],
        characters=characters,
    )


def write_snapshot(path: Path, snapshot: GeneratedContentSnapshot) -> None:
    write_json(path, snapshot.to_dict())


def read_snapshot(path: Path) -> GeneratedContentSnapshot:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("snapshot root must be an object")
    source_schema = data.get("schema_version")
    if source_schema not in _SUPPORTED_SNAPSHOT_SCHEMAS:
        raise ValueError(f"unsupported snapshot schema: {source_schema}")
    character_rows = data.get("characters")
    if not isinstance(character_rows, list):
        raise ValueError("snapshot characters must be an array")
    return GeneratedContentSnapshot(
        schema_version=int(source_schema),
        captured_at=_required_string(data, "captured_at"),
        book_name=_required_string(data, "book_name"),
        summary=_optional_string(data, "summary"),
        summary_generated_at=_optional_string(data, "summary_generated_at"),
        catalog_summary=_optional_string(data, "catalog_summary"),
        catalog_summary_generated_at=_optional_string(data, "catalog_summary_generated_at"),
        characters=tuple(_parse_character(row) for row in character_rows),
    )


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _parse_character(value: object) -> CharacterSnapshot:
    if not isinstance(value, dict):
        raise ValueError("snapshot character must be an object")
    return CharacterSnapshot(
        name=_required_string(value, "name"),
        summary=_optional_string(value, "summary"),
        first_page=_required_int(value, "first_page"),
        page_count=_required_int(value, "page_count"),
        generated_at=_optional_string(value, "generated_at"),
    )


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"snapshot {key} must be a non-empty string")
    return value


def _optional_string(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"snapshot {key} must be a string or null")
    return value


def _required_int(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"snapshot {key} must be an integer")
    return value
