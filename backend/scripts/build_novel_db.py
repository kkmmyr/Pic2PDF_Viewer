"""novel.db を CLI から構築する。

使用例（backend ディレクトリ内で実行）:

    cd backend
    uv run python scripts/build_novel_db.py --book "おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)"
    uv run python scripts/build_novel_db.py --book "おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)" --page 42
    uv run python scripts/build_novel_db.py --all
    uv run python scripts/build_novel_db.py --list

詳細は docs/design/詳細設計/機能別/小説RAG_パイプライン設計.md §3 を参照。
本スクリプトは Phase D3-2（ジョブキュー実装）後は内部で job_queue 経由に置き換える予定。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# backend/ をパスに追加（uv run python scripts/... 想定）
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from config import KINDLE_NOVEL_PDF_DIR
from services.novel_db import rebuild_book, rebuild_page_from_pages, with_db
from services.novel_db.migrations import upgrade_head


def _list_books() -> list[str]:
    pdf_dir = Path(KINDLE_NOVEL_PDF_DIR)
    if not pdf_dir.exists():
        return []
    return sorted(p.stem for p in pdf_dir.glob("*.pdf"))


def _print_progress(done: int, total: int) -> None:
    if total == 0:
        return
    print(f"  embedding {done}/{total}", flush=True)


def _rebuild_one(book_name: str) -> bool:
    print(f"[rebuild] {book_name}", flush=True)
    try:
        with with_db() as conn:
            rebuild_book(conn, book_name, progress_callback=_print_progress)
    except Exception as e:
        print(f"  FAILED: {e}", file=sys.stderr, flush=True)
        return False
    print("  OK", flush=True)
    return True


def _rebuild_one_page(book_name: str, page_no: int) -> bool:
    print(f"[rebuild-page] {book_name} p{page_no}", flush=True)
    try:
        with with_db() as conn:
            rebuild_page_from_pages(conn, book_name, page_no)
    except Exception as e:
        print(f"  FAILED: {e}", file=sys.stderr, flush=True)
        return False
    print("  OK", flush=True)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build novel.db from existing PDFs.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="全書籍を順次再構築する")
    group.add_argument("--book", metavar="NAME", help="指定書籍 1 冊を再構築する（PDF stem）")
    group.add_argument("--list", action="store_true", help="再構築可能な書籍一覧を表示する")
    parser.add_argument(
        "--page",
        type=int,
        metavar="PAGE_NO",
        help="--bookの指定ページだけを再構築する（1以上の画面番号）",
    )
    args = parser.parse_args(argv)

    if args.page is not None and (not args.book or args.page < 1):
        parser.error("--page requires --book and a page number greater than zero")

    upgrade_head()

    if args.list:
        books = _list_books()
        if not books:
            print(f"(no PDFs found in {KINDLE_NOVEL_PDF_DIR})")
            return 0
        for b in books:
            print(b)
        return 0

    if args.book:
        if args.page is not None:
            return 0 if _rebuild_one_page(args.book, args.page) else 1
        return 0 if _rebuild_one(args.book) else 1

    # --all
    books = _list_books()
    if not books:
        print(f"(no PDFs found in {KINDLE_NOVEL_PDF_DIR})", file=sys.stderr)
        return 1
    failed = [b for b in books if not _rebuild_one(b)]
    if failed:
        print(f"\n{len(failed)} book(s) failed:", file=sys.stderr)
        for b in failed:
            print(f"  - {b}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
