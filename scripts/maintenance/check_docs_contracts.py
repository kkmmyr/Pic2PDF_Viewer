"""登録済み横断契約の正本リンクとowner markerを検査する。"""

from __future__ import annotations

import json
import re
from pathlib import Path

OWNER_RE = re.compile(r"<!--\s*contract-owner:\s*([a-z0-9-]+)\s*-->")
LINK_RE = re.compile(r"\[(?:[^\]]*)\]\(([^)#\s][^)]*)\)")


def _canonical_map_links(index_file: Path, project_root: Path) -> set[str]:
    """正本マップ内のMarkdownリンクをproject root相対pathで返す。"""
    lines = index_file.read_text(encoding="utf-8", errors="replace").splitlines()
    in_map = False
    heading_seen = False
    section: list[str] = []
    for line in lines:
        if line.strip() == '<a id="canonical-map"></a>':
            in_map = True
            continue
        if not in_map:
            continue
        if line.startswith("## "):
            if heading_seen:
                break
            heading_seen = True
        section.append(line)

    links: set[str] = set()
    for match in LINK_RE.finditer("\n".join(section)):
        target = match.group(1).strip().split("#", maxsplit=1)[0]
        if not target or target.lower().startswith(("http://", "https://")):
            continue
        resolved = (index_file.parent / target).resolve()
        try:
            links.add(resolved.relative_to(project_root.resolve()).as_posix())
        except ValueError:
            continue
    return links


def _owner_occurrences(project_root: Path) -> dict[str, list[str]]:
    occurrences: dict[str, list[str]] = {}
    design_dir = project_root / "docs" / "design"
    for path in sorted(design_dir.rglob("*.md")):
        rel = path.relative_to(project_root).as_posix()
        for contract_id in OWNER_RE.findall(path.read_text(encoding="utf-8")):
            occurrences.setdefault(contract_id, []).append(rel)
    return occurrences


def _check_registered_contract(
    project_root: Path,
    contract_id: str,
    owner: str,
    links: set[str],
    occurrences: dict[str, list[str]],
) -> tuple[list[str], list[str]]:
    link_violations: list[str] = []
    marker_violations: list[str] = []
    if not (project_root / owner).exists():
        link_violations.append(f"{contract_id}: owner文書が存在しません ({owner})")
    if owner not in links:
        link_violations.append(
            f"{contract_id}: 正本マップにownerリンクがありません ({owner})"
        )
    locations = occurrences.get(contract_id, [])
    if not locations:
        marker_violations.append(f"{contract_id}: owner markerがありません ({owner})")
    elif locations != [owner]:
        marker_violations.append(
            f"{contract_id}: owner markerが正本以外または重複です ({', '.join(locations)})"
        )
    return link_violations, marker_violations


def find_violations(project_root: Path) -> tuple[list[str], list[str]]:
    """(正本マップリンク違反, owner marker違反)を返す。"""
    registry_path = project_root / "scripts" / "maintenance" / "docs_contracts.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    entries = registry.get("contracts", [])
    registered = {entry["id"]: entry["owner"] for entry in entries}

    occurrences = _owner_occurrences(project_root)
    link_violations: list[str] = []
    marker_violations: list[str] = []
    links = _canonical_map_links(project_root / "docs" / "index.md", project_root)

    if len(registered) != len(entries):
        marker_violations.append("docs_contracts.json: contract idが重複しています")

    for contract_id, owner in registered.items():
        contract_links, contract_markers = _check_registered_contract(
            project_root, contract_id, owner, links, occurrences
        )
        link_violations.extend(contract_links)
        marker_violations.extend(contract_markers)

    for contract_id, locations in occurrences.items():
        if contract_id not in registered:
            marker_violations.append(
                f"{contract_id}: 未登録のowner markerです ({', '.join(locations)})"
            )

    return sorted(link_violations), sorted(marker_violations)
