"""チャンク化戦略の比較実験スクリプト（§4.4）。

現状のページ単位チャンク（chunk_page, 800字/ページ）と
クロスページチャンク（chunk_book, 1200字/全文連結）の品質を比較する。
本番コード（builder.py）は変更せず、読み取り専用で既存 DB のページデータを使う。

使用例:
    cd backend

    # チャンク統計のみ表示（embedding 不要・高速）
    uv run python scripts/eval_chunk_strategy.py --book "おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)"

    # クエリに対するベクトル類似度トップ N を両方式で比較
    uv run python scripts/eval_chunk_strategy.py \\
        --book "おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)" \\
        --query "父王が次期女王を発表する場面"

    # 書籍一覧表示
    uv run python scripts/eval_chunk_strategy.py --list
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from services.novel_db import init_schema, with_db  # noqa: E402
from services.novel_db.chunker import chunk_book, chunk_page  # noqa: E402
from services.novel_db.embedder import embed_batch  # noqa: E402

_MIN_PAGE_CHARS = 30
_EMBED_BATCH = 16


# ---------------------------------------------------------------------------
# DB アクセス
# ---------------------------------------------------------------------------

def _list_books(conn) -> list[str]:
    return [r[0] for r in conn.execute("SELECT name FROM books ORDER BY name").fetchall()]


def _fetch_pages(conn, book_name: str) -> list[dict]:
    row = conn.execute("SELECT id FROM books WHERE name = ?", (book_name,)).fetchone()
    if row is None:
        raise ValueError(f"書籍が DB に見つかりません: {book_name!r}")
    book_id = row[0]
    rows = conn.execute(
        "SELECT id, page_no, full_text, char_count "
        "FROM pages WHERE book_id = ? ORDER BY page_no",
        (book_id,),
    ).fetchall()
    return [
        {"page_id": r[0], "page_no": r[1], "full_text": r[2] or "", "char_count": r[3] or 0}
        for r in rows
    ]


# ---------------------------------------------------------------------------
# チャンク生成
# ---------------------------------------------------------------------------

def _build_page_chunks(pages: list[dict]) -> list[dict]:
    """現状方式: ページ単位 chunk_page (800字)"""
    chunks = []
    for p in pages:
        if p["char_count"] < _MIN_PAGE_CHARS:
            continue
        for idx, c in enumerate(chunk_page(p["full_text"])):
            chunks.append({"page_id": p["page_id"], "page_no": p["page_no"], "chunk_idx": idx, "text": c})
    return chunks


def _build_book_chunks(pages: list[dict]) -> list[dict]:
    """実験方式: クロスページ chunk_book (1200字)"""
    pid_to_pno = {p["page_id"]: p["page_no"] for p in pages}
    return [
        {"page_id": c["page_id"], "page_no": pid_to_pno.get(c["page_id"], 0),
         "chunk_idx": c["chunk_idx"], "text": c["text"]}
        for c in chunk_book(pages)
    ]


# ---------------------------------------------------------------------------
# 統計表示
# ---------------------------------------------------------------------------

def _show_stats(label: str, chunks: list[dict]) -> None:
    if not chunks:
        print(f"  {label}: チャンクなし")
        return
    lengths = [len(c["text"]) for c in chunks]
    avg = sum(lengths) / len(lengths)
    print(f"  {label}")
    print(f"    チャンク数: {len(chunks)}")
    print(f"    文字数: avg {avg:.0f} / min {min(lengths)} / max {max(lengths)}")

    # 200 字ごとのバケット分布
    n_buckets = 9
    bucket_size = 200
    buckets = [0] * n_buckets
    for ln in lengths:
        idx = min(ln // bucket_size, n_buckets - 1)
        buckets[idx] += 1
    max_count = max(buckets) or 1
    print("    分布:")
    for i, cnt in enumerate(buckets):
        lo = i * bucket_size
        hi = (i + 1) * bucket_size - 1 if i < n_buckets - 1 else "+"
        bar = "█" * (cnt * 20 // max_count)
        label_str = f"{lo}-{hi}" if isinstance(hi, int) else f"{lo}{hi}"
        print(f"      {label_str:8s}: {cnt:4d}  {bar}")


# ---------------------------------------------------------------------------
# ベクトル類似度検索
# ---------------------------------------------------------------------------

def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na > 0 and nb > 0 else 0.0


def _embed_all(chunks: list[dict], label: str) -> list[dict]:
    texts = [c["text"] for c in chunks]
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), _EMBED_BATCH):
        batch = texts[i : i + _EMBED_BATCH]
        embeddings.extend(embed_batch(batch))
        done = min(i + _EMBED_BATCH, len(texts))
        print(f"  {label} embedding: {done}/{len(texts)}", end="\r", flush=True)
    print()
    return [dict(c, emb=e) for c, e in zip(chunks, embeddings, strict=True)]


def _top_n(query_emb: list[float], chunks: list[dict], n: int) -> list[dict]:
    scored = [(c, _cosine(query_emb, c["emb"])) for c in chunks]
    scored.sort(key=lambda x: -x[1])
    return [dict(c, score=s) for c, s in scored[:n]]


def _print_results(label: str, results: list[dict]) -> None:
    print(f"\n--- {label} ---")
    for r in results:
        preview = r["text"][:150].replace("\n", " ")
        print(f"  p{r['page_no']:>4d}  score={r['score']:.4f}  {preview}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="§4.4 チャンク戦略比較実験",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--book", metavar="NAME", help="書籍 stem（DB 登録名）")
    parser.add_argument("--query", metavar="Q", help="比較検索クエリ（省略時は統計のみ）")
    parser.add_argument("--top", type=int, default=5, help="表示件数（デフォルト 5）")
    parser.add_argument("--list", action="store_true", help="DB 登録済み書籍一覧を表示")
    args = parser.parse_args(argv)

    with with_db() as conn:
        init_schema(conn)

        if args.list:
            books = _list_books(conn)
            if not books:
                print("DB に書籍が登録されていません。")
            else:
                print(f"登録書籍 ({len(books)} 冊):")
                for b in books:
                    print(f"  {b}")
            return 0

        if not args.book:
            parser.print_help()
            return 1

        try:
            pages = _fetch_pages(conn, args.book)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    total_chars = sum(p["char_count"] for p in pages)
    print(f"\n=== {args.book} ===")
    print(f"ページ数: {len(pages)}  総文字数: {total_chars:,}\n")

    page_chunks = _build_page_chunks(pages)
    book_chunks = _build_book_chunks(pages)

    print("【チャンク統計】")
    _show_stats("現状 (chunk_page / 800字・ページ単位)", page_chunks)
    print()
    _show_stats("実験 (chunk_book / 1200字・クロスページ)", book_chunks)

    if not args.query:
        print("\n--query QUERY を指定するとベクトル類似度で両方式のトップ N を比較できます。")
        return 0

    print(f"\n【クエリ: {args.query!r}  top={args.top}】")
    print("embedding 計算中（Ollama bge-m3 が起動していること）...")

    query_emb = embed_batch([args.query])[0]
    page_chunks_emb = _embed_all(page_chunks, "現状")
    book_chunks_emb = _embed_all(book_chunks, "実験")

    _print_results(f"現状 (chunk_page) top {args.top}", _top_n(query_emb, page_chunks_emb, args.top))
    _print_results(f"実験 (chunk_book) top {args.top}", _top_n(query_emb, book_chunks_emb, args.top))

    print("\n（評価軸: 回答精度・根拠ページの妥当性・使い心地）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
