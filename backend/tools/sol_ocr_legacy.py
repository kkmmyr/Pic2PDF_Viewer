"""Snapshot current canonical OCR text as rollbackable legacy runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.novel_db.ocr_publication_history import snapshot_legacy_from_manifest
from services.novel_db.sol_ocr_campaign import verify_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--images-root", type=Path, required=True)
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--verified-backup", required=True)
    args = parser.parse_args()

    manifest = verify_manifest(args.manifest, args.images_root)
    result = snapshot_legacy_from_manifest(
        db_path=args.db_path,
        images_root=args.images_root,
        manifest=manifest,
        actor=args.actor,
        backup_reference=args.verified_backup,
    )
    print(json.dumps({"manifest_sha256": manifest["manifest_sha256"], **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
