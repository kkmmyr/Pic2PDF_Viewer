"""Explicit stage-one publication CLI; never starts embedding or OCR workers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.novel_db.connection import with_db
from services.novel_db.gpt61_body_publication import current_digest, publish_package


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["current", "publish"])
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--book")
    parser.add_argument("--images-root", type=Path)
    parser.add_argument("--package", type=Path)
    args = parser.parse_args()
    if args.command == "current":
        if not args.book:
            parser.error("--book required")
        with with_db(str(args.db_path)) as conn:
            result = {"book_name": args.book, "current_sha256": current_digest(conn, args.book)}
    else:
        if not args.package or not args.images_root:
            parser.error("--package and --images-root required")
        result = publish_package(
            db_path=args.db_path,
            images_root=args.images_root,
            package=json.loads(args.package.read_text(encoding="utf-8")),
        )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
