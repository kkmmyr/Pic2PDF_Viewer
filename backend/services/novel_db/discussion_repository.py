"""読書会history JSONの保存・照会・削除repository。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from utils.dt import JST
from utils.logger import get_logger
from utils.path_utils import resolve_under_base, validate_safe_name

logger = get_logger(__name__)
_FILENAME_RE = re.compile(r"^[\w+\-]+\.json$")


def discussion_book_dir(root: Path, book_name: str) -> Path:
    try:
        validate_safe_name(book_name, param_name="book_name")
        return Path(resolve_under_base(root, book_name, param_name="book_name"))
    except HTTPException as exc:
        raise ValueError(f"不正な書籍名です: {book_name}") from exc


def save_discussion(
    root: Path,
    book_name: str,
    cast_snapshot: list[dict],
    segments: list[dict],
    cards: list[dict],
    turns: list[dict],
    checks: dict,
) -> str:
    book_dir = discussion_book_dir(root, book_name)
    book_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(JST).strftime("%Y%m%dT%H%M%S%z")
    output = book_dir / f"{timestamp}.json"
    data = {
        "format_version": 2,
        "book": book_name,
        "cast": cast_snapshot,
        "segments": segments,
        "cards": cards,
        "turns": turns,
        "checks": checks,
        "partial": False,
        "created_at": datetime.now(JST).isoformat(),
    }
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(output)


def count_discussions(root: Path, book_name: str) -> int:
    book_dir = discussion_book_dir(root, book_name)
    return sum(1 for _ in book_dir.glob("*.json")) if book_dir.exists() else 0


def list_discussions(root: Path, book_name: str) -> list[dict]:
    book_dir = discussion_book_dir(root, book_name)
    if not book_dir.exists():
        return []
    results: list[dict] = []
    for path in sorted(book_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            version = data.get("format_version", 1)
            personas = _personas(data, version)
            results.append(
                {
                    "filename": path.name,
                    "created_at": data.get("created_at"),
                    "personas": personas,
                    "turn_count": len(data.get("turns", [])),
                    "turns": data.get("turns", []),
                    "format_version": version,
                    "segments": data.get("segments"),
                    "checks": data.get("checks"),
                }
            )
        except Exception:
            logger.warning("discussion JSON parse failed: %s", path.name, exc_info=True)
    return results


def delete_discussion(root: Path, book_name: str, filename: str) -> bool:
    if not _FILENAME_RE.match(filename):
        raise ValueError(f"不正なファイル名です: {filename}")
    target = Path(
        resolve_under_base(
            discussion_book_dir(root, book_name),
            filename,
            param_name="filename",
        )
    )
    if not target.exists():
        return False
    target.unlink()
    return True


def _personas(data: dict, version: object) -> list[dict]:
    if isinstance(version, int) and version >= 2:
        return [
            {"name": item.get("name", ""), "style_description": item.get("stance", "")} for item in data.get("cast", [])
        ]
    return data.get("personas", [])
