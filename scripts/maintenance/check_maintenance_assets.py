"""Validate compatibility, migration, and script ownership inventory."""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = Path(__file__).with_name("maintenance_assets.json")
VALID_COMPATIBILITY = {"maintain", "timeboxed", "removed"}
VALID_SCRIPT_CLASSES = {"continuous", "temporary", "frozen"}


def _required_text(entry: dict[str, Any], field: str, label: str) -> list[str]:
    value = entry.get(field)
    if isinstance(value, str) and value.strip():
        return []
    return [f"{label}: missing non-empty {field}"]


def _validate_recheck(
    entry: dict[str, Any],
    label: str,
    *,
    today: date,
) -> list[str]:
    raw = entry.get("recheck_after")
    if not isinstance(raw, str):
        return [f"{label}: timeboxed/temporary entry requires recheck_after"]
    try:
        recheck = date.fromisoformat(raw)
    except ValueError:
        return [f"{label}: invalid recheck_after {raw!r}"]
    if recheck <= today:
        return [f"{label}: recheck_after {raw} is due or expired"]
    return []


def validate_compatibility(
    entries: list[dict[str, Any]],
    project_root: Path,
    *,
    today: date,
) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        path = str(entry.get("path", ""))
        label = f"compatibility {path or '<missing-path>'}"
        if not path or path in seen:
            errors.append(f"{label}: path is missing or duplicated")
            continue
        seen.add(path)
        status = entry.get("status")
        if status not in VALID_COMPATIBILITY:
            errors.append(f"{label}: invalid status {status!r}")
            continue
        errors.extend(_required_text(entry, "owner", label))
        errors.extend(_required_text(entry, "evidence", label))
        errors.extend(_required_text(entry, "removal_condition", label))
        errors.extend(_required_text(entry, "rollback", label))
        exists = (project_root / path).is_file()
        if status == "removed" and exists:
            errors.append(f"{label}: removed path exists")
        if status != "removed" and not exists:
            errors.append(f"{label}: maintained path is missing")
        if status == "timeboxed":
            errors.extend(_validate_recheck(entry, label, today=today))
    return errors


def validate_migrations(
    entries: list[dict[str, Any]],
    project_root: Path,
    *,
    today: date,
) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        migration_id = str(entry.get("id", ""))
        label = f"migration {migration_id or '<missing-id>'}"
        if not migration_id or migration_id in seen:
            errors.append(f"{label}: id is missing or duplicated")
            continue
        seen.add(migration_id)
        for field in ("owner", "evidence", "removal_condition", "rollback"):
            errors.extend(_required_text(entry, field, label))
        path = str(entry.get("path", ""))
        if not path or not (project_root / path).is_file():
            errors.append(f"{label}: migration path is missing: {path!r}")
        if entry.get("status") != "timeboxed":
            errors.append(
                f"{label}: migration must remain timeboxed until removal audit"
            )
        errors.extend(_validate_recheck(entry, label, today=today))
    return errors


def classify_scripts(
    tracked_paths: list[str],
    groups: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    for path in tracked_paths:
        matched = [
            str(group.get("id", "<missing-id>"))
            for group in groups
            if any(
                PurePosixPath(path).match(pattern)
                for pattern in group.get("patterns", [])
            )
        ]
        if len(matched) != 1:
            errors.append(
                f"script {path}: expected one classification, found {matched}"
            )
    return errors


def validate_script_groups(
    groups: list[dict[str, Any]],
    tracked_paths: list[str],
    *,
    today: date,
) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for group in groups:
        group_id = str(group.get("id", ""))
        label = f"script group {group_id or '<missing-id>'}"
        if not group_id or group_id in seen:
            errors.append(f"{label}: id is missing or duplicated")
            continue
        seen.add(group_id)
        classification = group.get("classification")
        if classification not in VALID_SCRIPT_CLASSES:
            errors.append(f"{label}: invalid classification {classification!r}")
        for field in ("owner", "reason"):
            errors.extend(_required_text(group, field, label))
        patterns = group.get("patterns")
        if not isinstance(patterns, list) or not patterns:
            errors.append(f"{label}: patterns must be a non-empty list")
        if classification in {"temporary", "frozen"}:
            errors.extend(_validate_recheck(group, label, today=today))
    errors.extend(classify_scripts(tracked_paths, groups))
    return errors


def validate_ratchet_exceptions(
    entries: list[dict[str, Any]],
    project_root: Path,
    *,
    today: date,
) -> list[str]:
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        rule = str(entry.get("rule", ""))
        key = str(entry.get("key", ""))
        label = f"ratchet exception {rule or '<missing-rule>'} {key or '<missing-key>'}"
        identity = (rule, key)
        if rule not in {"code-size", "C901"}:
            errors.append(f"{label}: invalid rule")
        if not key or identity in seen:
            errors.append(f"{label}: key is missing or duplicated")
            continue
        seen.add(identity)
        for field in ("owner", "reason"):
            errors.extend(_required_text(entry, field, label))
        errors.extend(_validate_recheck(entry, label, today=today))
        source_path = key.split(":", 1)[0]
        if not (project_root / source_path).is_file():
            errors.append(f"{label}: source path is missing")
    return errors


def _tracked_scripts(project_root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "scripts"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        line.strip().replace("\\", "/")
        for line in completed.stdout.splitlines()
        if line.strip()
    ]


def find_errors(
    inventory: dict[str, Any],
    project_root: Path = PROJECT_ROOT,
    *,
    today: date | None = None,
    tracked_scripts: list[str] | None = None,
) -> list[str]:
    audit_date = today or date.today()
    tracked = (
        tracked_scripts
        if tracked_scripts is not None
        else _tracked_scripts(project_root)
    )
    errors = validate_compatibility(
        inventory.get("compatibility", []), project_root, today=audit_date
    )
    errors.extend(
        validate_migrations(
            inventory.get("migrations", []), project_root, today=audit_date
        )
    )
    errors.extend(
        validate_script_groups(
            inventory.get("script_groups", []), tracked, today=audit_date
        )
    )
    errors.extend(
        validate_ratchet_exceptions(
            inventory.get("ratchet_exceptions", []),
            project_root,
            today=audit_date,
        )
    )
    return sorted(errors)


def main() -> int:
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    errors = find_errors(inventory)
    if errors:
        print("Maintenance asset inventory check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Maintenance asset inventory check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
