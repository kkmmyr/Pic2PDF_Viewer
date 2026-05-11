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

詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md / 機能追加候補 B-9。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from config import NOVEL_DB_BODY_PAGE_MARGIN, NOVEL_DB_MIN_BODY_CHARS  # noqa: E402
from services.meta_store import load_meta  # noqa: E402
from services.novel_db import init_schema, with_db  # noqa: E402
from services.novel_db.contextualizer import (  # noqa: E402
    generate_chunk_context,
    make_embedding_input,
)
from services.novel_db.embedder import embed_batch, serialize_f32  # noqa: E402

# bge-m3 のバッチサイズ
_EMBED_BATCH_SIZE = 16


def _should_skip_context(char_count: int, page_no: int, page_count: int) -> bool:
    """ctx 生成を skip すべきチャンクか判定する。

    skip 条件:
    - char_count < NOVEL_DB_MIN_BODY_CHARS (300): 章扉・目次など薄いチャンク
    - page_no が先頭・末尾 NOVEL_DB_BODY_PAGE_MARGIN (5) ページ以内: 表紙・あとがき等

    skip 対象は ctx を NULL に保ち、検索 noise を避ける（B-9 改良 2026-05-12）。
    """
    if char_count < NOVEL_DB_MIN_BODY_CHARS:
        return True
    margin = NOVEL_DB_BODY_PAGE_MARGIN
    if page_no <= margin or page_no > page_count - margin:
        return True
    return False


def _list_target_books(
    *, book_name: str | None, series_id: str | None, redo: bool,
) -> list[tuple[int, str, str | None]]:
    """対象書籍を返す。各要素 (book_id, name, summary)。

    summary が NULL の書籍はスキップ（contextualize にはサマリが必要）。
    redo=False の場合、全チャンクが contextual_text 済みの書籍はスキップ。
    """
    with with_db() as conn:
        init_schema(conn)
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
        meta = load_meta("novel")
        series_books = {
            key[: -len(".pdf")]
            for key, entry in meta.items()
            if entry.get("series_id") == series_id and key.endswith(".pdf")
        }
        return [t for t in candidates if t[1] in series_books]
    return candidates


def _process_book(book_id: int, book_name: str, book_summary: str, *, redo: bool) -> tuple[int, int, int]:
    """1 冊のチャンクすべてに contextual_text を生成して chunks_vec を更新する。

    Returns: (success_count, skipped_count, failure_count)
    skipped は _should_skip_context により ctx 生成を意図的に省いた件数（B-9 改良 2026-05-12）。
    """
    with with_db() as conn:
        page_count_row = conn.execute(
            "SELECT page_count FROM books WHERE id = ?", (book_id,),
        ).fetchone()
        if page_count_row is None:
            print(f"  book not found: {book_name}", file=sys.stderr)
            return (0, 0, 0)
        page_count: int = page_count_row[0]

        if redo:
            chunks = conn.execute("""
                SELECT c.id, c.text, c.char_count, p.page_no
                FROM chunks c
                JOIN pages p ON c.page_id = p.id
                WHERE p.book_id = ?
                ORDER BY c.id
            """, (book_id,)).fetchall()
        else:
            chunks = conn.execute("""
                SELECT c.id, c.text, c.char_count, p.page_no
                FROM chunks c
                JOIN pages p ON c.page_id = p.id
                WHERE p.book_id = ? AND c.contextual_text IS NULL
                ORDER BY c.id
            """, (book_id,)).fetchall()

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
    pending_for_embed: list[tuple[int, str | None, str]] = []
    for i, (chunk_id, text, char_count, page_no) in enumerate(chunks, 1):
        if _should_skip_context(char_count, page_no, page_count):
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
                "contextual_generated_at = datetime('now') WHERE id = ?",
                (ctx, chunk_id),
            )
            conn.commit()
        pending_for_embed.append((chunk_id, ctx, text))
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
    for batch_start in range(0, len(pending_for_embed), _EMBED_BATCH_SIZE):
        batch = pending_for_embed[batch_start : batch_start + _EMBED_BATCH_SIZE]
        inputs = [make_embedding_input(ctx, text) for _, ctx, text in batch]
        try:
            embeds = embed_batch(inputs)
        except Exception as e:  # noqa: BLE001
            print(f"  embedding failed at batch {batch_start}: {e}", file=sys.stderr)
            continue
        with with_db() as conn:
            for (chunk_id, _ctx, _text), emb in zip(batch, embeds, strict=True):
                conn.execute("DELETE FROM chunks_vec WHERE rowid = ?", (chunk_id,))
                conn.execute(
                    "INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)",
                    (chunk_id, serialize_f32(emb)),
                )
            conn.commit()
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
    print(
        f"\n完了: {len(targets)} 冊 / chunks ok={total_ok} skip={total_skip} "
        f"ng={total_ng} ({elapsed:.0f}s)"
    )
    return 0 if total_ng == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
