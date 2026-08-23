"""Validate a Sol fact graph or its independent review without changing a DB."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from services.novel_db.sol_fact_graph import (
    apply_quote_repair,
    seal_candidate,
    validate_candidate,
    verify_review,
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _read_pages(path: Path) -> list[dict[str, Any]]:
    pages = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"pages line {line_number} must be an object")
            pages.append(value)
    return pages


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    candidate = commands.add_parser("validate-candidate")
    candidate.add_argument("--manifest", type=Path, required=True)
    candidate.add_argument("--pages", type=Path, required=True)
    candidate.add_argument("--candidate", type=Path, required=True)
    seal = commands.add_parser("seal-candidate")
    seal.add_argument("--manifest", type=Path, required=True)
    seal.add_argument("--pages", type=Path, required=True)
    seal.add_argument("--candidate", type=Path, required=True)
    seal.add_argument("--output", type=Path, required=True)
    repair = commands.add_parser("apply-quote-repair")
    repair.add_argument("--manifest", type=Path, required=True)
    repair.add_argument("--pages", type=Path, required=True)
    repair.add_argument("--candidate", type=Path, required=True)
    repair.add_argument("--repair", type=Path, required=True)
    repair.add_argument("--allow", action="append", required=True, help="Allowed fact and evidence index, e.g. F017:0")
    repair.add_argument("--output", type=Path, required=True)
    review = commands.add_parser("verify-review")
    review.add_argument("--manifest", type=Path, required=True)
    review.add_argument("--pages", type=Path, required=True)
    review.add_argument("--candidate", type=Path, required=True)
    review.add_argument("--review", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest = _read_json(args.manifest)
    pages = _read_pages(args.pages)
    candidate = _read_json(args.candidate)
    if args.command == "apply-quote-repair":
        allowed: list[tuple[str, int]] = []
        for value in args.allow:
            fact_id, separator, raw_index = value.partition(":")
            if not separator or not fact_id or not raw_index.isdigit():
                _parser().error("--allow must use FACT_ID:EVIDENCE_INDEX")
            allowed.append((fact_id, int(raw_index)))
        sealed = apply_quote_repair(
            candidate,
            _read_json(args.repair),
            allowed,
            pages,
            expected_source_sha256=manifest["source_sha256"],
        )
        args.output.write_text(
            json.dumps(sealed, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result = validate_candidate(sealed, pages, expected_source_sha256=manifest["source_sha256"])
    elif args.command == "seal-candidate":
        sealed = seal_candidate(candidate, pages, expected_source_sha256=manifest["source_sha256"])
        args.output.write_text(
            json.dumps(sealed, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result = validate_candidate(sealed, pages, expected_source_sha256=manifest["source_sha256"])
    elif args.command == "validate-candidate":
        result = validate_candidate(candidate, pages, expected_source_sha256=manifest["source_sha256"])
    else:
        result = verify_review(
            candidate,
            _read_json(args.review),
            pages,
            expected_source_sha256=manifest["source_sha256"],
            generation_run_id=manifest["run_id"],
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
