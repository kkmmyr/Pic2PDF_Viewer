"""Export or stage a sealed Codex-reviewed OCR package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.novel_db.codex_reviewed_ocr import (
    export_reviewed_run,
    load_reviewed_package,
    write_reviewed_package,
)
from services.novel_db.codex_reviewed_ocr_import import import_reviewed_package


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    export = subparsers.add_parser("export")
    export.add_argument("--db-path", type=Path, required=True)
    export.add_argument("--run-id", type=int, required=True)
    export.add_argument("--reviewer", required=True)
    export.add_argument("--review-note", required=True)
    export.add_argument("--output", type=Path, required=True)

    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("--db-path", type=Path, required=True)
    import_parser.add_argument("--images-root", type=Path, required=True)
    import_parser.add_argument("--package", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "export":
        package = export_reviewed_run(
            db_path=args.db_path,
            run_id=args.run_id,
            reviewer=args.reviewer,
            review_note=args.review_note,
        )
        write_reviewed_package(args.output, package)
        result = {
            "command": "export",
            "output": str(args.output.resolve()),
            "book_name": package["book_name"],
            "page_count": package["source_page_count"],
            "package_sha256": package["package_sha256"],
        }
    else:
        package = load_reviewed_package(args.package)
        result = {
            "command": "import",
            **import_reviewed_package(
                db_path=args.db_path,
                images_root=args.images_root,
                package=package,
            ),
        }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
