"""設計書検査が対象にするMarkdown sourceの列挙と分類。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from re import Pattern


def iter_link_checked_docs(
    docs_dir: Path, managed_module_docs: tuple[Path, ...]
) -> Iterator[Path]:
    """docs/と明示管理するmodule設計書をyieldする。"""
    yield from sorted(docs_dir.rglob("*.md"))
    yield from (path for path in managed_module_docs if path.exists())


def is_frozen_record(
    md_file: Path, docs_dir: Path, weekly_changelog_re: Pattern[str]
) -> bool:
    """archiveと週次変更履歴を凍結記録として分類する。"""
    try:
        parts = md_file.relative_to(docs_dir).parts
    except ValueError:
        return False
    return "archive" in parts or (
        "変更履歴" in parts and weekly_changelog_re.match(md_file.name) is not None
    )
