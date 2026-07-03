"""1 冊または全件のページから主要登場人物を抽出して novel.db に保存する。

使用例:
    cd backend
    uv run python scripts/extract_characters.py --book "おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)"
    uv run python scripts/extract_characters.py --all
    uv run python scripts/extract_characters.py --book "..." --redo  # 既存値を上書き

抽出は LLM (gemma4:12b) で行うため、1 ページあたり数秒〜十秒程度かかる。
1 冊（120 ページ）で 10〜20 分が目安。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from services.novel_db import with_db
from services.novel_db.character_extractor import extract_main_characters
from services.novel_db.migrations import upgrade_head


def _list_target_pages(book_name: str | None, redo: bool) -> list[tuple[int, str, int, str]]:
    """対象ページのリストを返す。各要素 (page_id, book_name, page_no, full_text)。"""
    with with_db() as conn:
        sql = (
            "SELECT p.id, b.name, p.page_no, p.full_text "
            "FROM pages p JOIN books b ON p.book_id = b.id "
            "WHERE p.full_text IS NOT NULL AND p.full_text != ''"
        )
        params: list = []
        if book_name:
            sql += " AND b.name = ?"
            params.append(book_name)
        if not redo:
            sql += " AND (p.main_characters IS NULL)"
        sql += " ORDER BY b.name, p.page_no"
        return conn.execute(sql, params).fetchall()


def _save(page_id: int, names: list[str]) -> None:
    with with_db() as conn:
        # 抽出済みだが該当なしは空文字で保存（NULL は未抽出と区別）
        conn.execute(
            "UPDATE pages SET main_characters = ? WHERE id = ?",
            (",".join(names), page_id),
        )
        conn.commit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract main characters per page.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--book", metavar="NAME", help="単冊（PDF stem）")
    group.add_argument("--all", action="store_true", help="全書籍")
    parser.add_argument("--redo", action="store_true", help="既存値を上書き")
    args = parser.parse_args(argv)
    upgrade_head()

    book_name = None if args.all else args.book
    targets = _list_target_pages(book_name, redo=args.redo)
    if not targets:
        print("(対象ページなし: 既に抽出済みか、書籍が存在しません。再抽出するには --redo を付けてください。)")
        return 0

    print(f"対象ページ: {len(targets)}")
    t0 = time.time()
    failures = 0
    for i, (page_id, book_name_, page_no, text) in enumerate(targets, 1):
        try:
            names = extract_main_characters(text)
            _save(page_id, names)
            elapsed = time.time() - t0
            avg = elapsed / i
            eta = avg * (len(targets) - i)
            print(
                f"  [{i}/{len(targets)}] {book_name_} p{page_no:3d}: {names} (avg {avg:.1f}s, eta {eta:.0f}s)",
                flush=True,
            )
        except Exception as e:
            failures += 1
            print(f"  [{i}/{len(targets)}] FAILED p{page_no}: {e}", file=sys.stderr)

    elapsed = time.time() - t0
    print(f"\n完了: {len(targets)} ページ ({elapsed:.0f}s, {failures} 件失敗)")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
