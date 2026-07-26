"""Fail when C901 complexity debt grows beyond the reviewed baseline."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = Path(__file__).with_name("c901_baseline.json")
MESSAGE_RE = re.compile(
    r"`(?P<symbol>[^`]+)` is too complex \((?P<complexity>\d+) > \d+\)"
)


@dataclass(frozen=True)
class ComplexityViolation:
    key: str
    complexity: int


def parse_ruff_output(
    payload: str, project_root: Path = PROJECT_ROOT
) -> list[ComplexityViolation]:
    records = json.loads(payload)
    violations: list[ComplexityViolation] = []
    for record in records:
        if record.get("code") != "C901":
            continue
        match = MESSAGE_RE.fullmatch(str(record.get("message", "")))
        if match is None:
            raise ValueError(f"unexpected C901 message: {record.get('message')}")
        path = (
            Path(str(record["filename"]))
            .resolve()
            .relative_to(project_root.resolve())
            .as_posix()
        )
        violations.append(
            ComplexityViolation(
                key=f"{path}:{match.group('symbol')}",
                complexity=int(match.group("complexity")),
            )
        )
    return violations


def find_regressions(
    baseline: dict[str, int],
    violations: list[ComplexityViolation],
) -> list[str]:
    regressions: list[str] = []
    for violation in violations:
        allowed = baseline.get(violation.key)
        if allowed is None:
            regressions.append(
                f"new C901 violation: {violation.key} = {violation.complexity}"
            )
        elif violation.complexity > allowed:
            regressions.append(
                f"C901 worsened: {violation.key} = {violation.complexity} (baseline {allowed})"
            )
    return regressions


def main() -> int:
    baseline: dict[str, int] = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    completed = subprocess.run(
        [
            "ruff",
            "check",
            "backend",
            "kindle-pdf",
            "--select",
            "C901",
            "--output-format",
            "json",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode not in {0, 1}:
        print(completed.stderr, file=sys.stderr)
        return completed.returncode
    violations = parse_ruff_output(completed.stdout)
    regressions = find_regressions(baseline, violations)
    if regressions:
        print("C901 complexity ratchet failed:")
        for regression in regressions:
            print(f"- {regression}")
        return 1

    observed_keys = {violation.key for violation in violations}
    improved = sorted(set(baseline) - observed_keys)
    print(f"C901 ratchet passed: {len(violations)} current / {len(baseline)} baseline")
    if improved:
        print(
            "Baseline entries now below threshold; remove them in a dedicated maintenance change:"
        )
        for key in improved:
            print(f"- {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
