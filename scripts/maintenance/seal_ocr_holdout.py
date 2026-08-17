"""Seal a B-35 formal holdout manifest and record its unopened ledger state."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from ocr_holdout_ledger import record_sealed_manifest
from ocr_holdout_manifest import build_formal_manifest


def _write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--corpus-json", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--operator", required=True)
    parser.add_argument("--sealed-at", required=True)
    args = parser.parse_args(argv)

    manifest = build_formal_manifest(
        json.loads(args.spec.read_text(encoding="utf-8")),
        json.loads(args.corpus_json.read_text(encoding="utf-8")),
        json.loads(args.policy.read_text(encoding="utf-8")),
        package_root=args.package_root,
        sealed_at=args.sealed_at,
    )
    _write_json_atomic(args.output, manifest)
    try:
        record_sealed_manifest(
            args.ledger,
            manifest,
            operator=args.operator,
            occurred_at=args.sealed_at,
        )
    except Exception:
        args.output.unlink(missing_ok=True)
        raise
    print(
        f"sealed={manifest['holdout_id']}, entries={len(manifest['entries'])}, "
        f"manifest_sha256={manifest['manifest_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
