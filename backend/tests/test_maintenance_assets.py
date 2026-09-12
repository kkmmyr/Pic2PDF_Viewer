"""Maintenance asset inventory validation tests."""

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "check_maintenance_assets.py"
_SPEC = importlib.util.spec_from_file_location("check_maintenance_assets", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
classify_scripts = _MODULE.classify_scripts
find_errors = _MODULE.find_errors


def test_page_fts_public_entry_is_registered_and_maintained() -> None:
    inventory = json.loads(_MODULE.INVENTORY_PATH.read_text(encoding="utf-8"))
    entries = [
        entry for entry in inventory["compatibility"] if entry["path"] == "backend/services/novel_db/page_fts.py"
    ]
    assert len(entries) == 1
    assert entries[0]["status"] == "maintain"
    assert entries[0]["owner"] == "novel-retrieval"
    assert _MODULE.validate_compatibility(entries, _MODULE.PROJECT_ROOT, today=date(2026, 9, 12)) == []


def test_classify_scripts_requires_exactly_one_group() -> None:
    groups = [
        {"id": "python", "patterns": ["scripts/*.py"]},
        {"id": "checks", "patterns": ["scripts/check_*.py"]},
    ]

    errors = classify_scripts(["scripts/run.py", "scripts/check_docs.py", "scripts/run.sh"], groups)

    assert "script scripts/check_docs.py: expected one classification" in errors[0]
    assert "script scripts/run.sh: expected one classification" in errors[1]


def test_find_errors_rejects_expired_timebox_and_restored_removed_file(
    tmp_path: Path,
) -> None:
    removed = tmp_path / "removed.py"
    removed.write_text("# restored", encoding="utf-8")
    migration = tmp_path / "migration.py"
    migration.write_text("# migration", encoding="utf-8")
    inventory = {
        "compatibility": [
            {
                "path": "removed.py",
                "status": "removed",
                "owner": "owner",
                "evidence": "unused",
                "removal_condition": "done",
                "rollback": "git restore",
                "recheck_after": None,
            }
        ],
        "migrations": [
            {
                "id": "legacy",
                "path": "migration.py",
                "status": "timeboxed",
                "owner": "owner",
                "evidence": "unknown clients",
                "removal_condition": "zero clients",
                "rollback": "restore importer",
                "recheck_after": "2026-01-01",
            }
        ],
        "script_groups": [],
    }

    errors = find_errors(
        inventory,
        tmp_path,
        today=date(2026, 8, 16),
        tracked_scripts=[],
    )

    assert any("removed path exists" in error for error in errors)
    assert any("is due or expired" in error for error in errors)
