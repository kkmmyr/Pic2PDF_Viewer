"""Run the monthly repository health audit from one reproducible command."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLAN_DIR = PROJECT_ROOT / "docs" / "log" / "計画"
PLAN_COORDINATORS = {
    "バックログ.md",
    "リファクタリング計画書.md",
    "設計書・ソースコード健全性維持計画.md",
}
STATUS_LINE_RE = re.compile(r"(?:>\s*状態|\*\*状態\*\*)\s*:\s*(?P<status>.+)$")
COMPLETION_MARKERS = ("完了", "通常運用へ移行")
ONGOING_MARKERS = ("実施中", "実装中", "進行中", "未達", "未完了", "保留", "待ち")


@dataclass(frozen=True)
class AuditCommand:
    name: str
    command: tuple[str, ...]
    cwd: Path = PROJECT_ROOT


def audit_commands(python: str = sys.executable) -> tuple[AuditCommand, ...]:
    script = PROJECT_ROOT / "scripts" / "maintenance"
    npm = shutil.which("npm") or "npm"
    return (
        AuditCommand("docs", (python, str(script / "check_docs.py"))),
        AuditCommand(
            "file-map",
            (python, str(script / "generate_file_map.py"), "--check"),
        ),
        AuditCommand(
            "code-size",
            (python, str(script / "check_code_size.py"), "--top", "10"),
        ),
        AuditCommand("C901", (python, str(script / "check_c901_ratchet.py"))),
        AuditCommand(
            "OpenAPI",
            (python, str(script / "check_openapi_contract.py")),
        ),
        AuditCommand(
            "import-boundaries",
            (python, str(script / "check_import_boundaries.py")),
        ),
        AuditCommand(
            "maintenance-assets",
            (python, str(script / "check_maintenance_assets.py")),
        ),
        AuditCommand(
            "frontend-unused",
            (npm, "run", "lint:deps"),
            PROJECT_ROOT / "frontend",
        ),
    )


def find_completed_plan_files(plan_dir: Path = PLAN_DIR) -> list[str]:
    completed: list[str] = []
    if not plan_dir.exists():
        return completed
    for path in sorted(plan_dir.glob("*.md")):
        if path.name in PLAN_COORDINATORS:
            continue
        head = path.read_text(encoding="utf-8", errors="replace").splitlines()[:30]
        if any(_is_completed_status(line) for line in head):
            try:
                relative = path.relative_to(PROJECT_ROOT)
            except ValueError:
                relative = Path("docs") / "log" / "計画" / path.name
            completed.append(relative.as_posix())
    return completed


def _is_completed_status(line: str) -> bool:
    match = STATUS_LINE_RE.search(line)
    if match is None:
        return False
    status = match.group("status")
    return any(marker in status for marker in COMPLETION_MARKERS) and not any(
        marker in status for marker in ONGOING_MARKERS
    )


def main() -> int:
    failed: list[str] = []
    print("=== Monthly repository health audit ===")
    for check in audit_commands():
        print(f"\n--- {check.name} ---", flush=True)
        completed = subprocess.run(
            check.command,
            cwd=check.cwd,
            check=False,
        )
        if completed.returncode != 0:
            failed.append(check.name)

    completed_plans = find_completed_plan_files()
    print("\n--- completed-plan residue ---")
    if completed_plans:
        failed.append("completed-plan residue")
        for path in completed_plans:
            print(f"- archive completed plan: {path}")
    else:
        print("No completed standalone plans remain in docs/log/計画.")

    if failed:
        print("\nMonthly health audit failed:")
        for name in failed:
            print(f"- {name}")
        return 1
    print("\nMonthly health audit passed. No persistent record is required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
