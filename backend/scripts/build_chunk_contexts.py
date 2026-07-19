"""1 冊または全件のチャンクに contextual_text を生成し、chunks_vec を再構築する。

使用例:
    cd backend
    uv run python scripts/build_chunk_contexts.py --book "おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)"
    uv run python scripts/build_chunk_contexts.py --all
    uv run python scripts/build_chunk_contexts.py --book "..." --redo  # 既存値を上書き

処理フロー（1 チャンクあたり）:
1. LLM で 80 字程度の位置説明を生成（gemma4:e4b 既定、~5 秒）
2. `chunks.contextual_text` に保存
3. `(contextual_text + chunk_text)` を bge-m3 で embedding
4. `chunks_vec` を DELETE → INSERT で更新

所要時間目安（gemma4:e4b、2,230 チャンクの全件）:
- 5 秒/chunk × 2,230 = 約 3 時間
- バッチサイズ 16 で embedding を流すので bge-m3 部分は無視できる

詳細は docs/design/詳細設計/機能別/小説RAG_パイプライン設計.md §5 / 機能追加候補 B-9。
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
from services.novel_db.contextualizer import (
    generate_chunk_context,
    make_embedding_input,
    should_skip_context,
)
from services.novel_db.embedder import embed_batch
from services.novel_db.lance_store import get_chunks_table
from services.novel_db.migrations import upgrade_head
from services.novel_db.series_meta import book_names_for_series

# bge-m3 のバッチサイズ
_EMBED_BATCH_SIZE = 16


def _list_target_books(
    *,
    book_name: str | None,
    series_id: str | None,
    redo: bool,
) -> list[tuple[int, str, str | None]]:
    """対象書籍を返す。各要素 (book_id, name, summary)。

    summary が NULL の書籍はスキップ（contextualize にはサマリが必要）。
    redo=False の場合、全チャンクが contextual_text 済みの書籍はスキップ。
    """
    with with_db() as conn:
        rows = conn.execute("""
            SELECT b.id, b.name, b.summary,
                   SUM(CASE WHEN c.contextual_text IS NULL THEN 1 ELSE 0 END) AS pending,
                   COUNT(c.id) AS total
            FROM books b
            LEFT JOIN pages p ON p.book_id = b.id
            LEFT JOIN chunks c ON c.page_id = p.id
            GROUP BY b.id
            ORDER BY b.id
        """).fetchall()

    candidates: list[tuple[int, str, str | None]] = []
    for book_id, name, summary, pending, total in rows:
        if not summary:
            print(f"  skip (no summary): {name[:50]}", file=sys.stderr)
            continue
        if not redo and (pending or 0) == 0 and (total or 0) > 0:
            print(f"  skip (already contextualized): {name[:50]}", file=sys.stderr)
            continue
        candidates.append((book_id, name, summary))

    if book_name is not None:
        return [t for t in candidates if t[1] == book_name]
    if series_id is not None:
        series_books = book_names_for_series(series_id)
        return [t for t in candidates if t[1] in series_books]
    return candidates


def _process_book(book_id: int, book_name: str, book_summary: str, *, redo: bool) -> tuple[int, int, int]:
    """1 冊のチャンクすべてに contextual_text を生成して chunks_vec を更新する。

    Returns: (success_count, skipped_count, failure_count)
    skipped は _should_skip_context により ctx 生成を意図的に省いた件数（B-9 改良 2026-05-12）。
    """
    with with_db() as conn:
        page_count_row = conn.execute(
            "SELECT page_count FROM books WHERE id = ?",
            (book_id,),
        ).fetchone()
        if page_count_row is None:
            print(f"  book not found: {book_name}", file=sys.stderr)
            return (0, 0, 0)
        page_count: int = page_count_row[0]

        if redo:
            chunks = conn.execute(
                """
                SELECT c.id, c.text, c.char_count, p.page_no
                FROM chunks c
                JOIN pages p ON c.page_id = p.id
                WHERE p.book_id = ?
                ORDER BY c.id
            """,
                (book_id,),
            ).fetchall()
        else:
            chunks = conn.execute(
                """
                SELECT c.id, c.text, c.char_count, p.page_no
                FROM chunks c
                JOIN pages p ON c.page_id = p.id
                WHERE p.book_id = ? AND c.contextual_text IS NULL
                ORDER BY c.id
            """,
                (book_id,),
            ).fetchall()

    if not chunks:
        print(f"  no pending chunks for {book_name}", flush=True)
        return (0, 0, 0)

    print(f"  {len(chunks)} chunks to process", flush=True)

    success = 0
    failure = 0
    skipped = 0
    t0 = time.time()
    # コンテキスト生成 → DB 更新（embedding は最後にバッチで）
    # ctx は str | None。skip 対象は None を保ち、make_embedding_input が text のみで embed する。
    pending_for_embed: list[tuple[int, str | None, str, int, int]] = []
    for i, (chunk_id, text, char_count, page_no) in enumerate(chunks, 1):
        if should_skip_context(char_count, page_no, page_count):
            ctx: str | None = None
            skipped += 1
        else:
            generated = generate_chunk_context(book_name, book_summary, text)
            if generated:
                ctx = generated
                success += 1
            else:
                ctx = None
                failure += 1
        with with_db() as conn:
            conn.execute(
                "UPDATE chunks SET contextual_text = ?, "
                "contextual_generated_at = datetime('now', '+9 hours') WHERE id = ?",
                (ctx, chunk_id),
            )
            conn.commit()
        pending_for_embed.append((chunk_id, ctx, text, page_no, char_count or 0))
        if i % 10 == 0 or i == len(chunks):
            elapsed = time.time() - t0
            avg = elapsed / i
            eta = avg * (len(chunks) - i)
            print(
                f"  ctx [{i:>4}/{len(chunks)}] avg {avg:.1f}s/chunk "
                f"ok={success} skip={skipped} ng={failure} eta {eta:.0f}s",
                flush=True,
            )

    # embedding バッチ
    print(f"  re-embedding {len(pending_for_embed)} chunks ...", flush=True)
    t1 = time.time()
    lance_table = get_chunks_table()
    for batch_start in range(0, len(pending_for_embed), _EMBED_BATCH_SIZE):
        batch = pending_for_embed[batch_start : batch_start + _EMBED_BATCH_SIZE]
        inputs = [make_embedding_input(ctx, text) for _, ctx, text, _page_no, _char_count in batch]
        try:
            embeds = embed_batch(inputs)
        except Exception as e:
            print(f"  embedding failed at batch {batch_start}: {e}", file=sys.stderr)
            continue
        # book_name / page_count は関数冒頭で取得済み、page_no / char_count は上の
        # ctx 生成ループで取得済みのため、chunk_id ごとの再 JOIN クエリ (N+1) は不要。
        lance_rows = [
            {
                "chunk_id": chunk_id,
                "book_name": book_name,
                "page_no": page_no,
                "text": _text,
                "char_count": char_count,
                "page_count": page_count or 0,
                "embedding": emb,
            }
            for (chunk_id, _ctx, _text, page_no, char_count), emb in zip(batch, embeds, strict=True)
        ]
        if lance_rows:
            chunk_ids = [r["chunk_id"] for r in lance_rows]
            ids_str = ", ".join(str(cid) for cid in chunk_ids)
            lance_table.delete(f"chunk_id IN ({ids_str})")
            lance_table.add(lance_rows)
    print(f"  embedding done ({time.time() - t1:.0f}s)", flush=True)
    return (success, skipped, failure)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build chunk contextual text and re-embed.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--book", metavar="NAME", help="単冊（PDF stem）")
    group.add_argument("--series", metavar="ID", help="シリーズ ID")
    group.add_argument("--all", action="store_true", help="全書籍")
    parser.add_argument("--redo", action="store_true", help="既存 contextual_text を上書き")
    args = parser.parse_args(argv)
    upgrade_head()

    targets = _list_target_books(
        book_name=args.book,
        series_id=args.series,
        redo=args.redo,
    )
    if not targets:
        print("(対象なし。書籍に summary が無いか、既に contextualize 済み)")
        return 0

    print(f"対象書籍: {len(targets)}")
    t0 = time.time()
    total_ok, total_skip, total_ng = 0, 0, 0
    for i, (book_id, name, summary) in enumerate(targets, 1):
        print(f"\n[{i}/{len(targets)}] {name}", flush=True)
        ok, skip, ng = _process_book(book_id, name, summary, redo=args.redo)
        total_ok += ok
        total_skip += skip
        total_ng += ng
        elapsed = time.time() - t0
        avg = elapsed / i
        eta = avg * (len(targets) - i)
        print(
            f"  book done. cumulative ok={total_ok} skip={total_skip} ng={total_ng} "
            f"(elapsed {elapsed:.0f}s, eta {eta:.0f}s)",
            flush=True,
        )

    elapsed = time.time() - t0
    print(f"\n完了: {len(targets)} 冊 / chunks ok={total_ok} skip={total_skip} ng={total_ng} ({elapsed:.0f}s)")
    return 0 if total_ng == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
