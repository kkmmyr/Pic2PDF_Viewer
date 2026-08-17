"""Apply an isolated E18 repair or verify a fresh 41-claim Sol review."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from services.novel_db.generated_content_snapshot import write_json
from services.novel_db.sol_risk_cycle import (
    apply_single_claim_repair,
    verify_independent_review,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    apply_repair = commands.add_parser("apply-repair")
    apply_repair.add_argument("--candidate", type=Path, required=True)
    apply_repair.add_argument("--repair", type=Path, required=True)
    apply_repair.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify-review")
    verify.add_argument("--candidate", type=Path, required=True)
    verify.add_argument("--review", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)
    return parser


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    candidate = _read(args.candidate)
    if args.command == "apply-repair":
        repaired = apply_single_claim_repair(candidate, _read(args.repair))
        write_json(args.output, repaired)
        print(f"repaired candidate saved: {args.output}")
        return 0
    result = verify_independent_review(candidate, _read(args.review))
    write_json(args.output, result)
    print(f"independent review: PASS ({result['supported_count']} supported)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
