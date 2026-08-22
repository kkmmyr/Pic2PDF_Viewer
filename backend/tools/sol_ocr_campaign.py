"""Create or verify immutable Sol image-OCR campaign manifests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from services.novel_db.sol_ocr_campaign import (
        create_manifest,
        create_pilot_manifest,
        export_pilot_images,
        load_pilot_manifest,
        verify_manifest,
    )
except ImportError:  # Standalone copy used for a server-side read-only manifest pass.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "novel_db"))
    from sol_ocr_campaign import (
        create_manifest,
        create_pilot_manifest,
        export_pilot_images,
        load_pilot_manifest,
        verify_manifest,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create-manifest")
    create.add_argument("--images-root", type=Path, required=True)
    create.add_argument("--db-path", type=Path)
    create.add_argument("--output-dir", type=Path, required=True)
    create.add_argument("--campaign-id", required=True)
    create.add_argument("--workers", type=int, default=3)
    verify = subparsers.add_parser("verify-manifest")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--images-root", type=Path, required=True)
    verify.add_argument("--skip-images", action="store_true")
    pilot = subparsers.add_parser("create-pilot")
    pilot.add_argument("--manifest", type=Path, required=True)
    pilot.add_argument("--images-root", type=Path, required=True)
    pilot.add_argument("--output", type=Path, required=True)
    export = subparsers.add_parser("export-pilot")
    export.add_argument("--pilot", type=Path, required=True)
    export.add_argument("--images-root", type=Path, required=True)
    export.add_argument("--output-tar", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "create-manifest":
        manifest = create_manifest(
            images_root=args.images_root,
            db_path=args.db_path,
            output_dir=args.output_dir,
            campaign_id=args.campaign_id,
            worker_count=args.workers,
        )
    elif args.command == "verify-manifest":
        manifest = verify_manifest(
            args.manifest,
            args.images_root,
            verify_images=not args.skip_images,
        )
    elif args.command == "create-pilot":
        campaign_manifest = verify_manifest(args.manifest, args.images_root, verify_images=False)
        pilot_manifest = create_pilot_manifest(campaign_manifest=campaign_manifest, output_path=args.output)
        print(
            json.dumps(
                {"pilot_sha256": pilot_manifest["pilot_sha256"], **pilot_manifest["summary"]},
                ensure_ascii=False,
            )
        )
        return 0
    else:
        pilot_manifest = load_pilot_manifest(args.pilot)
        export_pilot_images(
            pilot_manifest=pilot_manifest,
            images_root=args.images_root,
            output_tar=args.output_tar,
        )
        print(json.dumps({"pilot_sha256": pilot_manifest["pilot_sha256"], **pilot_manifest["summary"]}))
        return 0
    print(json.dumps({"manifest_sha256": manifest["manifest_sha256"], **manifest["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
