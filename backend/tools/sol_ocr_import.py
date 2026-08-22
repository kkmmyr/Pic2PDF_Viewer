"""Validate/import Sol OCR pilot artifacts and emit a legacy-difference report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.novel_db.sol_ocr_campaign import load_pilot_manifest, verify_manifest
from services.novel_db.sol_ocr_import import (
    build_pilot_comparison_report,
    build_pilot_review_package,
    import_pilot_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--images-root", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--review-package", type=Path)
    args = parser.parse_args()

    campaign = verify_manifest(args.manifest, args.images_root, verify_images=False)
    pilot = load_pilot_manifest(args.pilot)
    artifact_paths = sorted(args.artifacts.glob("worker-*/*.json"))
    result = import_pilot_artifacts(
        db_path=args.db_path,
        campaign_manifest=campaign,
        pilot_manifest=pilot,
        images_root=args.images_root,
        artifact_paths=artifact_paths,
    )
    report = build_pilot_comparison_report(db_path=args.db_path, pilot_manifest=pilot)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.review_package is not None:
        review = build_pilot_review_package(db_path=args.db_path, pilot_manifest=pilot)
        args.review_package.parent.mkdir(parents=True, exist_ok=True)
        args.review_package.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**result, "comparison": report["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
