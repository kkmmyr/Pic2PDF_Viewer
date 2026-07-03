"""1 冊または全件の書籍サマリ（あらすじ）を Qwen で生成して novel.db に保存する。

使用例:
    cd backend
    uv run python scripts/build_novel_summaries.py --book "おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)"
    uv run python scripts/build_novel_summaries.py --all
    uv run python scripts/build_novel_summaries.py --all --redo   # 既存値を上書き
    uv run python scripts/build_novel_summaries.py --series "おこぼれ姫"

サマリは LLM (qwen3.6:35b-a3b) で map-reduce 方式で生成するため、1 冊あたり 5〜15 分
程度かかる。11 冊で 1.5〜2 時間が目安。

詳細は docs/design/詳細設計/機能別/小説RAG_パイプライン設計.md §4。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from services.meta_store import load_meta
from services.novel_db import with_db
from services.novel_db.migrations import upgrade_head
from services.novel_db.summarizer import (
    summarize_book,
    update_book_summary,
)


def _list_target_books(
    *,
    book_name: str | None,
    series_id: str | None,
    redo: bool,
) -> list[str]:
    """サマリ生成対象の書籍名リストを返す。"""
    with with_db() as conn:
        sql = "SELECT name, summary FROM books"
        rows = conn.execute(sql).fetchall()

    candidates: list[str] = [name for name, summary in rows if (redo or not summary)]

    if book_name is not None:
        if book_name not in candidates:
            # --book 指定のときは redo の有無に関わらずチェック対象に
            return [book_name] if any(name == book_name for name, _ in rows) else []
        return [book_name]

    if series_id is not None:
        meta = load_meta("novel")
        series_books = {
            key[: -len(".pdf")]
            for key, entry in meta.items()
            if entry.get("series_id") == series_id and key.endswith(".pdf")
        }
        return [name for name in candidates if name in series_books]

    return candidates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build per-book summaries.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--book", metavar="NAME", help="単冊（PDF stem）")
    group.add_argument("--series", metavar="ID", help="シリーズ ID")
    group.add_argument("--all", action="store_true", help="全書籍")
    parser.add_argument("--redo", action="store_true", help="既存値を上書き")
    args = parser.parse_args(argv)
    upgrade_head()

    targets = _list_target_books(
        book_name=args.book,
        series_id=args.series,
        redo=args.redo,
    )
    if not targets:
        print(
            "(対象なし: 既に summary 生成済み、または該当書籍が DB に存在しません。"
            "再生成するには --redo を付けてください。)",
        )
        return 0

    print(f"対象書籍: {len(targets)}")
    t0 = time.time()
    failures = 0
    for i, name in enumerate(targets, 1):
        print(f"\n[{i}/{len(targets)}] {name}", flush=True)
        try:
            with with_db() as conn:
                summary = summarize_book(
                    conn,
                    name,
                    progress=lambda msg: print(msg, flush=True),
                )
                update_book_summary(conn, name, summary)
            elapsed = time.time() - t0
            avg = elapsed / i
            eta = avg * (len(targets) - i)
            print(
                f"  done: {len(summary):,} chars (elapsed {elapsed:.0f}s, avg {avg:.0f}s/book, eta {eta:.0f}s)",
                flush=True,
            )
        except Exception as e:
            failures += 1
            print(f"  FAILED: {e}", file=sys.stderr, flush=True)

    elapsed = time.time() - t0
    print(f"\n完了: {len(targets)} 冊 ({elapsed:.0f}s, {failures} 件失敗)")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
