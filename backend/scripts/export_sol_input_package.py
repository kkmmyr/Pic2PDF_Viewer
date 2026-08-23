"""Export OCR-approved pages for an isolated Sol fact-graph job."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from services.novel_db.sol_job_package import export_input_package


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--book", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--privacy-acknowledged-at", required=True)
    parser.add_argument("--canonical-names", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--max-input-chars", type=int, default=300_000)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    names: list[str] = []
    if args.canonical_names is not None:
        value = json.loads(args.canonical_names.read_text(encoding="utf-8"))
        if not isinstance(value, list) or any(not isinstance(name, str) for name in value):
            _parser().error("--canonical-names must contain a JSON string array")
        names = value
    manifest = export_input_package(
        database_path=args.db,
        book_name=args.book,
        output_dir=args.output_dir,
        privacy_acknowledged_at=args.privacy_acknowledged_at,
        canonical_names=names,
        run_id=args.run_id,
        max_input_chars=args.max_input_chars,
    )
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
