"""設計書ファイルマップの手書き注釈を検査する。"""

from __future__ import annotations

import re
from pathlib import Path

MD_LINK_RE = re.compile(r"\[(?:[^\]]*)\]\(([^)#\s][^)]*)\)")
FILE_MAP_SECTION_HEADING = "## 2. 主要ファイル補足"


def find_violations(project_root: Path) -> list[str]:
    """主要ファイル補足のMarkdownリンクが実在するか検査する。"""
    detail_dir = project_root / "docs" / "design" / "詳細設計"
    file_map_docs = [
        detail_dir / "詳細設計書_フロントエンド_ファイルマップ.md",
        detail_dir / "詳細設計書_バックエンド_ファイルマップ.md",
    ]
    violations: list[str] = []
    for md_file in file_map_docs:
        rel_file = md_file.relative_to(project_root)
        if not md_file.exists():
            violations.append(f"{rel_file}: ファイルが存在しません")
            continue
        lines = md_file.read_text(encoding="utf-8", errors="replace").splitlines()
        section_start = next(
            (
                i
                for i, line in enumerate(lines)
                if line.strip() == FILE_MAP_SECTION_HEADING
            ),
            None,
        )
        if section_start is None:
            violations.append(
                f"{rel_file}: 「{FILE_MAP_SECTION_HEADING}」セクションが見つかりません"
            )
            continue
        section_end = next(
            (
                i
                for i in range(section_start + 1, len(lines))
                if lines[i].startswith("## ")
            ),
            len(lines),
        )
        for offset, line in enumerate(lines[section_start:section_end]):
            match = MD_LINK_RE.search(line) if line.strip().startswith("|") else None
            if not match:
                continue
            target = match.group(1).strip()
            if target.lower().startswith(("http://", "https://")):
                continue
            if not (md_file.parent / target).resolve().exists():
                lineno = section_start + offset + 1
                violations.append(f"{rel_file}:{lineno} -> {target}（実在しません）")
    return violations
