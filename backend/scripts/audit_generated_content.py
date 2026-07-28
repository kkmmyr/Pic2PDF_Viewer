"""Snapshot, diff, or restore generated novel summaries and character entries."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from services.novel_db.connection import with_db
from services.novel_db.generated_content_audit import (
    build_generated_content_diff,
    capture_generated_content,
    read_snapshot,
    restore_generated_content,
    write_diff_report,
    write_snapshot,
)
from services.novel_db.summarizer import index_book_summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit generated summaries and character prose for one novel.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Optional novel.db path. The configured production database is used by default.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser("snapshot", help="Save the current published prose.")
    snapshot.add_argument("--book", required=True)
    snapshot.add_argument("--output", type=Path, required=True)

    diff = subparsers.add_parser("diff", help="Compare a snapshot with the current database.")
    diff.add_argument("--before", type=Path, required=True)
    diff.add_argument("--json-output", type=Path, required=True)
    diff.add_argument("--markdown-output", type=Path, required=True)

    restore = subparsers.add_parser("restore", help="Restore a saved snapshot.")
    restore.add_argument("--snapshot", type=Path, required=True)
    restore.add_argument(
        "--confirm-book",
        required=True,
        help="Exact book name required to authorize the restore.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "snapshot":
        with with_db(args.db_path) as conn:
            snapshot = capture_generated_content(conn, args.book)
        write_snapshot(args.output, snapshot)
        print(f"snapshot saved: {args.output}")
        return 0

    snapshot = read_snapshot(args.before if args.command == "diff" else args.snapshot)
    if args.command == "diff":
        with with_db(args.db_path) as conn:
            after = capture_generated_content(conn, snapshot.book_name)
        report = build_generated_content_diff(snapshot, after)
        write_diff_report(
            json_path=args.json_output,
            markdown_path=args.markdown_output,
            report=report,
        )
        quality = "PASS" if report["quality"]["passed"] else "FAIL"
        print(f"diff saved: {args.json_output}")
        print(f"review report saved: {args.markdown_output}")
        print(f"mechanical quality gate: {quality}")
        return 0 if report["quality"]["passed"] else 2

    with with_db(args.db_path) as conn:
        book_id, summary = restore_generated_content(
            conn,
            snapshot,
            confirmed_book_name=args.confirm_book,
        )
        if summary:
            index_book_summary(conn, book_id, summary, raise_on_error=True)
    print(f"snapshot restored: {snapshot.book_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
