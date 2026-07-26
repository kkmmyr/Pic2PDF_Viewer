from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "check_c901_ratchet.py"
_SPEC = importlib.util.spec_from_file_location("check_c901_ratchet", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
ratchet = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = ratchet
_SPEC.loader.exec_module(ratchet)


def test_parse_ruff_output_uses_stable_path_and_symbol_key(tmp_path) -> None:
    target = tmp_path / "backend" / "service.py"
    payload = json.dumps(
        [
            {
                "code": "C901",
                "filename": str(target),
                "message": "`process` is too complex (13 > 10)",
            }
        ]
    )

    assert ratchet.parse_ruff_output(payload, tmp_path) == [
        ratchet.ComplexityViolation("backend/service.py:process", 13)
    ]


def test_find_regressions_rejects_new_and_worsened_violations() -> None:
    baseline = {"backend/a.py:existing": 12}
    violations = [
        ratchet.ComplexityViolation("backend/a.py:existing", 13),
        ratchet.ComplexityViolation("backend/b.py:new", 11),
    ]

    assert ratchet.find_regressions(baseline, violations) == [
        "C901 worsened: backend/a.py:existing = 13 (baseline 12)",
        "new C901 violation: backend/b.py:new = 11",
    ]


def test_find_regressions_allows_same_or_improved_complexity() -> None:
    baseline = {"backend/a.py:existing": 12}

    assert (
        ratchet.find_regressions(
            baseline,
            [ratchet.ComplexityViolation("backend/a.py:existing", 11)],
        )
        == []
    )
