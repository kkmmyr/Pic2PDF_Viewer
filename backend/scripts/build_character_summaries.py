"""B-15 キャラクター辞典: 書籍 × キャラの人物像サマリを一括生成する CLI。

使用例:
    cd backend
    uv run python scripts/build_character_summaries.py --book "おこぼれ姫と..."
    uv run python scripts/build_character_summaries.py --all
    uv run python scripts/build_character_summaries.py --book "..." --redo
    uv run python scripts/build_character_summaries.py --book "..." --character "レティ"

処理フロー（1 書籍あたり）:
1. `pages.main_characters` を集計してキャラ統計を作成（character_summarizer.list_book_characters_in_db）
2. 各キャラについて以下を実施:
   - 統計値（first_page / page_count）を `book_characters` に UPSERT
   - 該当キャラを含むページの本文を集めて Qwen に投入 → 1 段落サマリを生成
   - `book_characters.summary` を更新
3. `--redo` でなければ既に summary を持つキャラはスキップ

所要時間目安: 1 キャラあたり 30〜90 秒（Qwen / llama-server、書籍内出現量による）。
1 冊 5 キャラ × 60 秒 ≒ 5 分 / 全 11 冊 ≒ 1 時間弱。

詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §5.10 / B-15。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from services.meta_store import load_meta  # noqa: E402
from services.novel_db import init_schema, with_db  # noqa: E402
from services.novel_db.character_summarizer import (  # noqa: E402
    collect_character_pages,
    list_book_characters_in_db,
    summarize_character,
    upsert_character,
)


def _list_target_books(
    *, book_name: str | None, series_id: str | None,
) -> list[tuple[int, str]]:
    """対象書籍 (book_id, name) を返す。summary 未生成かどうかは呼び出し側で判定。"""
    with with_db() as conn:
        init_schema(conn)
        rows = conn.execute(
            "SELECT id, name FROM books ORDER BY id",
        ).fetchall()
    candidates = [(book_id, name) for book_id, name in rows]

    if book_name is not None:
        return [t for t in candidates if t[1] == book_name]
    if series_id is not None:
        meta = load_meta("novel")
        series_books = {
            key[: -len(".pdf")]
            for key, entry in meta.items()
            if entry.get("series_id") == series_id and key.endswith(".pdf")
        }
        return [t for t in candidates if t[1] in series_books]
    return candidates


def _existing_summaries(conn, book_id: int) -> set[str]:
    """既に summary が入っているキャラ名集合を返す。"""
    rows = conn.execute(
        """
        SELECT name FROM book_characters
        WHERE book_id = ? AND summary IS NOT NULL AND summary <> ''
        """,
        (book_id,),
    ).fetchall()
    return {r[0] for r in rows}


def _process_book(
    book_id: int,
    book_name: str,
    *,
    redo: bool,
    only_character: str | None,
) -> tuple[int, int, int]:
    """1 冊のキャラを処理する。

    Returns: (success_count, skipped_count, failure_count)
    skipped は「既に summary 済みで --redo 未指定」または「pages が空」のケース。
    """
    with with_db() as conn:
        stats = list_book_characters_in_db(conn, book_id)
        existing = set() if redo else _existing_summaries(conn, book_id)

    if only_character is not None:
        stats = [s for s in stats if s.name == only_character]
        if not stats:
            print(f"  character '{only_character}' not found in {book_name}", file=sys.stderr)
            return (0, 0, 0)

    if not stats:
        print(f"  no characters extracted for {book_name}", flush=True)
        return (0, 0, 0)

    print(f"  {len(stats)} characters detected (top: "
          f"{', '.join(s.name for s in stats[:5])})", flush=True)

    success = 0
    skipped = 0
    failure = 0
    t0 = time.time()
    for i, stat in enumerate(stats, 1):
        # 統計値は常に UPSERT する（summary 未生成のときも first_page / page_count は持っておく）
        if stat.name in existing:
            with with_db() as conn:
                upsert_character(conn, book_id, stat, summary=None)
            print(f"  [{i}/{len(stats)}] skip (already summarized): {stat.name}",
                  flush=True)
            skipped += 1
            continue

        with with_db() as conn:
            pages = collect_character_pages(conn, book_id, stat.name)
        if not pages:
            print(f"  [{i}/{len(stats)}] skip (no pages): {stat.name}", flush=True)
            with with_db() as conn:
                upsert_character(conn, book_id, stat, summary=None)
            skipped += 1
            continue

        body_chars = sum(len(t) for _, t in pages)
        print(f"  [{i}/{len(stats)}] {stat.name} "
              f"(pages={len(pages)} body_chars={body_chars:,}) ...",
              flush=True)
        try:
            summary = summarize_character(book_name, stat.name, pages)
        except Exception as e:  # noqa: BLE001
            print(f"    ng: {e}", file=sys.stderr)
            failure += 1
            with with_db() as conn:
                upsert_character(conn, book_id, stat, summary=None)
            continue

        with with_db() as conn:
            upsert_character(conn, book_id, stat, summary=summary)
        elapsed = time.time() - t0
        avg = elapsed / i
        eta = avg * (len(stats) - i)
        print(f"    ok ({len(summary)} chars) elapsed={elapsed:.0f}s eta={eta:.0f}s",
              flush=True)
        success += 1

    return (success, skipped, failure)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build per-character summaries for novel_db books (B-15).",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--book", metavar="NAME", help="単冊（PDF stem）")
    group.add_argument("--series", metavar="ID", help="シリーズ ID")
    group.add_argument("--all", action="store_true", help="全書籍")
    parser.add_argument("--redo", action="store_true", help="既存 summary を上書き")
    parser.add_argument("--character", metavar="NAME", default=None,
                        help="このキャラのみ生成（--book と併用、--all 時は全冊から該当キャラを探す）")
    args = parser.parse_args(argv)

    targets = _list_target_books(book_name=args.book, series_id=args.series)
    if not targets:
        print("(対象書籍なし)")
        return 0

    print(f"対象書籍: {len(targets)}")
    t0 = time.time()
    total_ok, total_skip, total_ng = 0, 0, 0
    for i, (book_id, name) in enumerate(targets, 1):
        print(f"\n[{i}/{len(targets)}] {name}", flush=True)
        ok, skip, ng = _process_book(
            book_id, name, redo=args.redo, only_character=args.character,
        )
        total_ok += ok
        total_skip += skip
        total_ng += ng
        elapsed = time.time() - t0
        print(f"  book done. cumulative ok={total_ok} skip={total_skip} ng={total_ng} "
              f"(elapsed {elapsed:.0f}s)", flush=True)

    elapsed = time.time() - t0
    print(
        f"\n完了: {len(targets)} 冊 / characters ok={total_ok} "
        f"skip={total_skip} ng={total_ng} ({elapsed:.0f}s)"
    )
    return 0 if total_ng == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
