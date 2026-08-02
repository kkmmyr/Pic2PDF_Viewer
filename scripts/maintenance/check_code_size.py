"""Prevent production source files from growing beyond a reviewed size baseline."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = Path(__file__).with_name("code_size_baseline.json")
LINE_LIMIT = 400
SOURCE_ROOTS = (
    Path("backend"),
    Path("kindle-pdf"),
    Path("frontend/src"),
)
SOURCE_SUFFIXES = {".py", ".ts", ".tsx"}
EXCLUDED_PARTS = {
    ".venv",
    "__pycache__",
    "__tests__",
    "archive",
    "data",
    "fixtures",
    "migrations",
    "node_modules",
    "tests",
}


def is_production_source(path: Path) -> bool:
    """Return whether a repository-relative path belongs to production code."""
    normalized = Path(path.as_posix())
    parts = normalized.parts
    if normalized.suffix not in SOURCE_SUFFIXES:
        return False
    if any(part in EXCLUDED_PARTS for part in parts):
        return False
    if "alembic" in parts and "versions" in parts:
        return False
    name = normalized.name
    if name == "api.d.ts" or name == "vite-env.d.ts":
        return False
    if ".test." in name or ".spec." in name or name.startswith("test_"):
        return False
    return any(normalized.is_relative_to(root) for root in SOURCE_ROOTS)


def collect_line_counts(project_root: Path = PROJECT_ROOT) -> dict[str, int]:
    counts: dict[str, int] = {}
    for source_root in SOURCE_ROOTS:
        absolute_root = project_root / source_root
        if not absolute_root.exists():
            continue
        for current_dir, dirnames, filenames in os.walk(absolute_root):
            dirnames[:] = [
                dirname for dirname in dirnames if dirname not in EXCLUDED_PARTS
            ]
            for filename in filenames:
                path = Path(current_dir) / filename
                relative = path.relative_to(project_root)
                if not is_production_source(relative):
                    continue
                counts[relative.as_posix()] = len(
                    path.read_text(encoding="utf-8", errors="replace").splitlines()
                )
    return dict(sorted(counts.items()))


def find_regressions(
    baseline: dict[str, int],
    current: dict[str, int],
) -> list[str]:
    regressions: list[str] = []
    for path, line_count in sorted(current.items()):
        allowed = baseline.get(path)
        if allowed is None and line_count > LINE_LIMIT:
            regressions.append(
                f"new oversized production file: {path} = {line_count} lines "
                f"(limit {LINE_LIMIT})"
            )
        elif allowed is not None and line_count > allowed:
            regressions.append(
                f"code size worsened: {path} = {line_count} lines (baseline {allowed})"
            )
    return regressions


def oversized_counts(counts: dict[str, int]) -> dict[str, int]:
    return {path: count for path, count in counts.items() if count > LINE_LIMIT}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update",
        action="store_true",
        help="replace the baseline with current files above the line limit",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=0,
        metavar="N",
        help="print the N largest production source files",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    current = collect_line_counts()
    if args.top > 0:
        print(f"Largest {args.top} production source files:")
        for path, count in sorted(
            current.items(), key=lambda item: (-item[1], item[0])
        )[: args.top]:
            print(f"- {count:5d}  {path}")

    if args.update:
        baseline = oversized_counts(current)
        BASELINE_PATH.write_text(
            json.dumps(baseline, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"Code-size baseline updated: {len(baseline)} files")
        return 0

    if not BASELINE_PATH.exists():
        print(
            f"Code-size baseline is missing: {BASELINE_PATH.relative_to(PROJECT_ROOT)}",
            file=sys.stderr,
        )
        return 2
    baseline: dict[str, int] = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    regressions = find_regressions(baseline, current)
    if regressions:
        print("Code-size ratchet failed:")
        for regression in regressions:
            print(f"- {regression}")
        return 1

    improved = sorted(
        path
        for path, allowed in baseline.items()
        if path not in current or current[path] <= LINE_LIMIT or current[path] < allowed
    )
    print(
        f"Code-size ratchet passed: {len(oversized_counts(current))} current / "
        f"{len(baseline)} baseline files above {LINE_LIMIT} lines"
    )
    if improved:
        print("Baseline entries improved; refresh in a dedicated maintenance change:")
        for path in improved:
            current_count = current.get(path, 0)
            print(f"- {path}: {current_count} (baseline {baseline[path]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
