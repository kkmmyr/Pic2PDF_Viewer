"""
gemma4:e4b vs gemma4:12b — CONTEXT_MODEL / QA_EXPAND_MODEL 比較スクリプト

Usage:
    cd backend
    uv run python scripts/compare_context_expand.py
"""

import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from services.novel_db.contextualizer import generate_chunk_context
from services.novel_db.query_expander import expand_query

MODELS = ["gemma4:e4b", "gemma4:12b"]
DB_PATH = "data/novel_db/novel.db"

# ── テスト用クエリ（QA_EXPAND_MODEL） ────────────────────────────────────
TEST_QUERIES = [
    "レティとデュークの関係はどう変化したか",
    "主人公が初めて魔法を使った場面",
    "仲間との別れのシーン",
]


# ── コンテキスト生成用サンプル取得 ────────────────────────────────────────
def get_context_samples(n: int = 3):
    """(book_name, book_summary, chunk_text) を n 件取得。"""
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        """
        SELECT b.name, b.summary, c.text
        FROM chunks c
        JOIN pages p ON c.page_id = p.id
        JOIN books b ON p.book_id = b.id
        WHERE length(c.text) > 200
          AND b.summary IS NOT NULL
          AND length(b.summary) > 50
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (n,),
    ).fetchall()
    con.close()
    return rows


# ── 1. CONTEXT_MODEL 比較 ─────────────────────────────────────────────────
def compare_context():
    print("=" * 60)
    print("【NOVEL_DB_CONTEXT_MODEL 比較】チャンク位置説明生成")
    print("=" * 60)
    samples = get_context_samples(3)
    if not samples:
        print("ERROR: サンプルが取得できませんでした（book.summary が未生成？）")
        return

    times = {m: 0.0 for m in MODELS}

    for i, (book, summary, chunk) in enumerate(samples, 1):
        print(f"\n【サンプル {i}】{book[:40]}")
        print(f"  チャンク冒頭: {chunk[:80].strip()}...")
        print()
        for model in MODELS:
            t0 = time.perf_counter()
            result = generate_chunk_context(
                book_name=book,
                book_summary=summary,
                chunk_text=chunk,
                model=model,
            )
            elapsed = time.perf_counter() - t0
            times[model] += elapsed
            print(f"  {model:20s} ({elapsed:.1f}s)")
            print(f"    → {result}")
        print()

    print("【合計時間】")
    n = len(samples)
    for model in MODELS:
        print(f"  {model:20s}: 合計 {times[model]:.1f}s  平均 {times[model] / n:.1f}s/チャンク")


# ── 2. QA_EXPAND_MODEL 比較 ──────────────────────────────────────────────
def compare_expand():
    print()
    print("=" * 60)
    print("【NOVEL_DB_QA_EXPAND_MODEL 比較】クエリ展開")
    print("=" * 60)

    times = {m: 0.0 for m in MODELS}

    for i, query in enumerate(TEST_QUERIES, 1):
        print(f"\n【質問 {i}】{query}")
        for model in MODELS:
            t0 = time.perf_counter()
            expanded = expand_query(query, n=3, model=model)
            elapsed = time.perf_counter() - t0
            times[model] += elapsed
            print(f"  {model:20s} ({elapsed:.1f}s)")
            for q in expanded:
                print(f"    • {q}")
        print()

    print("【合計時間】")
    n = len(TEST_QUERIES)
    for model in MODELS:
        print(f"  {model:20s}: 合計 {times[model]:.1f}s  平均 {times[model] / n:.1f}s/クエリ")


if __name__ == "__main__":
    compare_context()
    compare_expand()
