"""Validate a Sol publication artifact or its independent review without DB writes."""

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

from services.novel_db.sol_publication import (
    validate_publication,
    verify_publication_review,
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _read_pages(path: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, start=1):
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"pages line {number} must be an object")
            values.append(value)
    return values


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    publication = commands.add_parser("validate-publication")
    review = commands.add_parser("verify-review")
    for command in (publication, review):
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument("--pages", type=Path, required=True)
        command.add_argument("--candidate", type=Path, required=True)
        command.add_argument("--publication", type=Path, required=True)
    review.add_argument("--review", type=Path, required=True)
    review.add_argument("--writing-run-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest = _read_json(args.manifest)
    pages = _read_pages(args.pages)
    candidate = _read_json(args.candidate)
    publication = _read_json(args.publication)
    if args.command == "validate-publication":
        result = validate_publication(
            publication,
            candidate,
            pages,
            expected_source_sha256=manifest["source_sha256"],
        )
    else:
        result = verify_publication_review(
            publication,
            candidate,
            _read_json(args.review),
            pages,
            expected_source_sha256=manifest["source_sha256"],
            writing_run_id=args.writing_run_id,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
