"""CLI for selecting and operating a sealed Sol image-OCR holdout."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from services.novel_db.sol_ocr_holdout import (
        create_formal_holdout_manifest,
        export_formal_holdout_images,
        load_formal_holdout_manifest,
        open_formal_holdout,
        record_sealed_manifest,
        retire_formal_holdout_to_tuning,
        verify_formal_holdout_manifest,
    )
except ImportError:  # Standalone copy used during the server-side campaign pass.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "novel_db"))
    from sol_ocr_holdout import (
        create_formal_holdout_manifest,
        export_formal_holdout_images,
        load_formal_holdout_manifest,
        open_formal_holdout,
        record_sealed_manifest,
        retire_formal_holdout_to_tuning,
        verify_formal_holdout_manifest,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--campaign", type=Path, required=True)
    create.add_argument("--exclude-pilot", type=Path, action="append", default=[], dest="pilots")
    create.add_argument("--b35", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--holdout-id", required=True)
    create.add_argument("--seed", required=True)
    create.add_argument("--prompt-sha256", required=True)
    create.add_argument("--policy-sha256", required=True)
    create.add_argument("--canonical-books", type=int, required=True)
    create.add_argument("--image-only-books", type=int, required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--campaign", type=Path, required=True)
    verify.add_argument("--exclude-pilot", type=Path, action="append", default=[], dest="pilots")
    verify.add_argument("--b35", type=Path, required=True)

    record = subparsers.add_parser("record-sealed")
    record.add_argument("--manifest", type=Path, required=True)
    record.add_argument("--ledger", type=Path, required=True)
    record.add_argument("--operator", required=True)

    opened = subparsers.add_parser("open")
    opened.add_argument("--manifest", type=Path, required=True)
    opened.add_argument("--ledger", type=Path, required=True)
    opened.add_argument("--operator", required=True)
    opened.add_argument("--reason", required=True)

    export = subparsers.add_parser("export")
    export.add_argument("--manifest", type=Path, required=True)
    export.add_argument("--campaign", type=Path, required=True)
    export.add_argument("--exclude-pilot", type=Path, action="append", default=[], dest="pilots")
    export.add_argument("--b35", type=Path, required=True)
    export.add_argument("--ledger", type=Path, required=True)
    export.add_argument("--images-root", type=Path, required=True)
    export.add_argument("--output-tar", type=Path, required=True)

    retire = subparsers.add_parser("retire")
    retire.add_argument("--manifest", type=Path, required=True)
    retire.add_argument("--ledger", type=Path, required=True)
    retire.add_argument("--operator", required=True)
    retire.add_argument("--reason", required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "create":
        result = create_formal_holdout_manifest(
            campaign_manifest_path=args.campaign,
            pilot_manifest_paths=args.pilots,
            b35_manifest_path=args.b35,
            output_path=args.output,
            holdout_id=args.holdout_id,
            seed=args.seed,
            prompt_sha256=args.prompt_sha256,
            policy_sha256=args.policy_sha256,
            canonical_books=args.canonical_books,
            image_only_books=args.image_only_books,
        )
        print(json.dumps({"manifest_sha256": result["manifest_sha256"], "samples": len(result["samples"])}))
    elif args.command == "verify":
        manifest = load_formal_holdout_manifest(args.manifest)
        print(
            json.dumps(
                verify_formal_holdout_manifest(
                    manifest,
                    campaign_manifest_path=args.campaign,
                    pilot_manifest_paths=args.pilots,
                    b35_manifest_path=args.b35,
                ),
                sort_keys=True,
            )
        )
    elif args.command == "export":
        manifest = load_formal_holdout_manifest(args.manifest)
        verify_formal_holdout_manifest(
            manifest,
            campaign_manifest_path=args.campaign,
            pilot_manifest_paths=args.pilots,
            b35_manifest_path=args.b35,
        )
        export_formal_holdout_images(
            manifest=manifest,
            ledger_path=args.ledger,
            images_root=args.images_root,
            output_tar=args.output_tar,
        )
        print(json.dumps({"command": args.command, "manifest_sha256": manifest["manifest_sha256"]}))
    else:
        manifest = load_formal_holdout_manifest(args.manifest)
        if args.command == "record-sealed":
            record_sealed_manifest(args.ledger, manifest, operator=args.operator)
        elif args.command == "open":
            open_formal_holdout(args.ledger, manifest, operator=args.operator, reason=args.reason)
        else:
            retire_formal_holdout_to_tuning(args.ledger, manifest, operator=args.operator, reason=args.reason)
        print(json.dumps({"command": args.command, "manifest_sha256": manifest["manifest_sha256"]}))


if __name__ == "__main__":
    main()
