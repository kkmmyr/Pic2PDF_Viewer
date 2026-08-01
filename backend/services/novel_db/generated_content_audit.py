"""Snapshot, compare, and restore generated book summaries and character prose."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from ._prompts import CATALOG_SUMMARY_MAX_CHARS, CATALOG_SUMMARY_MIN_CHARS
from .generation_quality import generated_prose_issues

SNAPSHOT_SCHEMA_VERSION = 2
_SUPPORTED_SNAPSHOT_SCHEMAS = {1, SNAPSHOT_SCHEMA_VERSION}


@dataclass(frozen=True)
class CharacterSnapshot:
    """One published character entry."""

    name: str
    summary: str | None
    first_page: int
    page_count: int
    generated_at: str | None


@dataclass(frozen=True)
class GeneratedContentSnapshot:
    """Restorable generated prose for one book."""

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
    """Read the currently published generated prose without mutating the database."""
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
        FROM book_characters
        WHERE book_id = ?
        ORDER BY name
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
    """Atomically write a UTF-8 JSON snapshot."""
    _write_json(path, snapshot.to_dict())


def read_snapshot(path: Path) -> GeneratedContentSnapshot:
    """Read and validate a snapshot created by this module."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("snapshot root must be an object")
    source_schema = data.get("schema_version")
    if source_schema not in _SUPPORTED_SNAPSHOT_SCHEMAS:
        raise ValueError(f"unsupported snapshot schema: {data.get('schema_version')}")

    character_rows = data.get("characters")
    if not isinstance(character_rows, list):
        raise ValueError("snapshot characters must be an array")
    characters = tuple(_parse_character(row) for row in character_rows)
    return GeneratedContentSnapshot(
        schema_version=int(source_schema),
        captured_at=_required_string(data, "captured_at"),
        book_name=_required_string(data, "book_name"),
        summary=_optional_string(data, "summary"),
        summary_generated_at=_optional_string(data, "summary_generated_at"),
        catalog_summary=_optional_string(data, "catalog_summary"),
        catalog_summary_generated_at=_optional_string(data, "catalog_summary_generated_at"),
        characters=characters,
    )


def build_generated_content_diff(
    before: GeneratedContentSnapshot,
    after: GeneratedContentSnapshot,
) -> dict[str, Any]:
    """Build a complete, machine-readable before/after report."""
    if before.book_name != after.book_name:
        raise ValueError(f"book mismatch: {before.book_name} != {after.book_name}")

    before_chars = {character.name: character for character in before.characters}
    after_chars = {character.name: character for character in after.characters}
    added = sorted(after_chars.keys() - before_chars.keys())
    removed = sorted(before_chars.keys() - after_chars.keys())
    shared = sorted(before_chars.keys() & after_chars.keys())
    changed = [
        _character_change(before_chars[name], after_chars[name])
        for name in shared
        if before_chars[name] != after_chars[name]
    ]

    after_summary = after.summary or ""
    after_catalog_summary = after.catalog_summary or ""
    character_issues = {
        character.name: generated_prose_issues(
            character.summary or "",
            required_subject=character.name,
        )
        for character in after.characters
    }
    character_issues = {name: issues for name, issues in character_issues.items() if issues}
    summary_issues = generated_prose_issues(after_summary)
    catalog_summary_issues = generated_prose_issues(after_catalog_summary)
    catalog_length = len(after_catalog_summary)
    if not CATALOG_SUMMARY_MIN_CHARS <= catalog_length <= CATALOG_SUMMARY_MAX_CHARS:
        catalog_summary_issues.append(
            f"catalog summary length must be {CATALOG_SUMMARY_MIN_CHARS}-{CATALOG_SUMMARY_MAX_CHARS}: "
            f"{catalog_length}"
        )
    summary_changed = before.summary != after.summary
    catalog_summary_changed = before.catalog_summary != after.catalog_summary
    review_required = summary_changed or catalog_summary_changed or bool(added or removed or changed)

    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "book_name": before.book_name,
        "compared_at": datetime.now(UTC).isoformat(),
        "before": before.to_dict(),
        "after": after.to_dict(),
        "summary_change": {
            "changed": summary_changed,
            "before_chars": len(before.summary or ""),
            "after_chars": len(after_summary),
            "similarity": _similarity(before.summary, after.summary),
            "generated_at_changed": before.summary_generated_at != after.summary_generated_at,
        },
        "catalog_summary_change": {
            "changed": catalog_summary_changed,
            "before_chars": len(before.catalog_summary or ""),
            "after_chars": catalog_length,
            "similarity": _similarity(before.catalog_summary, after.catalog_summary),
            "generated_at_changed": (
                before.catalog_summary_generated_at != after.catalog_summary_generated_at
            ),
        },
        "character_changes": {
            "added": added,
            "removed": removed,
            "changed": changed,
            "before_count": len(before.characters),
            "after_count": len(after.characters),
        },
        "quality": {
            "passed": (
                not summary_issues
                and not catalog_summary_issues
                and not character_issues
                and bool(after.characters)
            ),
            "summary_issues": summary_issues,
            "catalog_summary_issues": catalog_summary_issues,
            "character_issues": character_issues,
            "no_characters": not after.characters,
        },
        "review": {
            "required": review_required,
            "targets": [
                *(["summary"] if summary_changed else []),
                *(["catalog_summary"] if catalog_summary_changed else []),
                *[f"character:{name}" for name in added],
                *[f"character:{name}" for name in removed],
                *[f"character:{item['name']}" for item in changed],
            ],
        },
    }


def render_diff_markdown(report: dict[str, Any]) -> str:
    """Render a human-reviewable report containing the changed prose in full."""
    before = report["before"]
    after = report["after"]
    summary_change = report["summary_change"]
    catalog_summary_change = report["catalog_summary_change"]
    character_changes = report["character_changes"]
    quality = report["quality"]

    lines = [
        f"# 生成内容差分監査: {report['book_name']}",
        "",
        f"- 比較日時: `{report['compared_at']}`",
        f"- 要約変更: `{summary_change['changed']}` "
        f"（{summary_change['before_chars']} → {summary_change['after_chars']}文字、"
        f"類似度 {summary_change['similarity']:.3f}）",
        f"- 一覧向け短縮要約変更: `{catalog_summary_change['changed']}` "
        f"（{catalog_summary_change['before_chars']} → {catalog_summary_change['after_chars']}文字、"
        f"類似度 {catalog_summary_change['similarity']:.3f}）",
        f"- 人物数: {character_changes['before_count']} → {character_changes['after_count']}",
        f"- 機械品質ゲート: `{'PASS' if quality['passed'] else 'FAIL'}`",
        f"- Codex補助QA: `{'required' if report['review']['required'] else 'not required'}`",
        "",
        "## 人物集合の差分",
        "",
        f"- 追加: {_join_names(character_changes['added'])}",
        f"- 削除: {_join_names(character_changes['removed'])}",
        f"- 変更: {_join_names([item['name'] for item in character_changes['changed']])}",
        "",
        "## 機械品質ゲート",
        "",
        f"- 要約: {_join_names(quality['summary_issues'])}",
        f"- 一覧向け短縮要約: {_join_names(quality['catalog_summary_issues'])}",
        f"- 人物なし: `{quality['no_characters']}`",
    ]
    character_issues = quality["character_issues"]
    if character_issues:
        lines.extend(f"- {name}: {_join_names(issues)}" for name, issues in character_issues.items())
    else:
        lines.append("- 人物説明: 問題なし")

    if summary_change["changed"]:
        lines.extend(
            [
                "",
                "## 要約（変更前）",
                "",
                before["summary"] or "（なし）",
                "",
                "## 要約（変更後）",
                "",
                after["summary"] or "（なし）",
            ]
        )

    if catalog_summary_change["changed"]:
        lines.extend(
            [
                "",
                "## 一覧向け短縮要約（変更前）",
                "",
                before["catalog_summary"] or "（なし）",
                "",
                "## 一覧向け短縮要約（変更後）",
                "",
                after["catalog_summary"] or "（なし）",
            ]
        )

    before_chars = {item["name"]: item for item in before["characters"]}
    after_chars = {item["name"]: item for item in after["characters"]}
    changed_names = [
        *character_changes["added"],
        *character_changes["removed"],
        *[item["name"] for item in character_changes["changed"]],
    ]
    for name in dict.fromkeys(changed_names):
        old = before_chars.get(name)
        new = after_chars.get(name)
        lines.extend(
            [
                "",
                f"## 人物: {name}",
                "",
                "### 変更前",
                "",
                old["summary"] if old and old["summary"] else "（なし）",
                "",
                "### 変更後",
                "",
                new["summary"] if new and new["summary"] else "（なし）",
            ]
        )
    return "\n".join(lines) + "\n"


def restore_generated_content(
    conn: sqlite3.Connection,
    snapshot: GeneratedContentSnapshot,
    *,
    confirmed_book_name: str,
) -> tuple[int, str | None]:
    """Transactionally restore SQLite rows after an exact book-name confirmation."""
    if confirmed_book_name != snapshot.book_name:
        raise ValueError("confirmed book name does not exactly match the snapshot")
    row = conn.execute(
        "SELECT id FROM books WHERE name = ?",
        (snapshot.book_name,),
    ).fetchone()
    if row is None:
        raise ValueError(f"book not found: {snapshot.book_name}")
    book_id = int(row["id"])

    try:
        conn.execute("BEGIN IMMEDIATE")
        if snapshot.schema_version >= 2:
            conn.execute(
                """
                UPDATE books
                SET summary = ?, summary_generated_at = ?,
                    catalog_summary = ?, catalog_summary_generated_at = ?
                WHERE id = ?
                """,
                (
                    snapshot.summary,
                    snapshot.summary_generated_at,
                    snapshot.catalog_summary,
                    snapshot.catalog_summary_generated_at,
                    book_id,
                ),
            )
        else:
            conn.execute(
                "UPDATE books SET summary = ?, summary_generated_at = ? WHERE id = ?",
                (snapshot.summary, snapshot.summary_generated_at, book_id),
            )
        conn.execute("DELETE FROM book_characters WHERE book_id = ?", (book_id,))
        conn.executemany(
            """
            INSERT INTO book_characters
                (book_id, name, summary, first_page, page_count, generated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    book_id,
                    character.name,
                    character.summary,
                    character.first_page,
                    character.page_count,
                    character.generated_at,
                )
                for character in snapshot.characters
            ],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return book_id, snapshot.summary


def _character_change(
    before: CharacterSnapshot,
    after: CharacterSnapshot,
) -> dict[str, Any]:
    return {
        "name": before.name,
        "summary_changed": before.summary != after.summary,
        "before_chars": len(before.summary or ""),
        "after_chars": len(after.summary or ""),
        "similarity": _similarity(before.summary, after.summary),
        "first_page": [before.first_page, after.first_page],
        "page_count": [before.page_count, after.page_count],
        "generated_at_changed": before.generated_at != after.generated_at,
    }


def _similarity(before: str | None, after: str | None) -> float:
    return SequenceMatcher(None, before or "", after or "").ratio()


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


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_diff_report(
    *,
    json_path: Path,
    markdown_path: Path,
    report: dict[str, Any],
) -> None:
    """Atomically write both machine-readable and review-oriented reports."""
    _write_json(json_path, report)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = markdown_path.with_suffix(markdown_path.suffix + ".tmp")
    temporary.write_text(render_diff_markdown(report), encoding="utf-8")
    temporary.replace(markdown_path)


def _join_names(values: list[str]) -> str:
    return "、".join(values) if values else "なし"
