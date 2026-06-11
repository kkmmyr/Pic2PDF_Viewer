"""
gemma4:e4b vs gemma4:12b — キャラクター抽出 比較スクリプト

Usage:
    cd backend
    uv run python scripts/compare_char_extract.py
"""

import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from services.novel_db.character_extractor import extract_main_characters

DB_PATH = "data/novel_db/novel.db"
MODELS = ["gemma4:e4b", "gemma4:12b"]
N_SAMPLES = 5


def get_samples(n: int) -> list[tuple[str, str]]:
    """(book_name, page_text) をランダムに n 件取得。"""
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        """
        SELECT b.name, p.full_text
        FROM pages p
        JOIN books b ON p.book_id = b.id
        WHERE length(p.full_text) > 400
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (n,),
    ).fetchall()
    con.close()
    return rows


def run_comparison():
    print("サンプル取得中...")
    samples = get_samples(N_SAMPLES)
    if not samples:
        print("ERROR: サンプルが取得できませんでした")
        return

    print(f"\n{'=' * 60}")
    print(f"サンプル数: {len(samples)} ページ")
    print(f"{'=' * 60}\n")

    results: dict[str, list] = {m: [] for m in MODELS}
    times: dict[str, float] = {m: 0.0 for m in MODELS}

    for i, (book, text) in enumerate(samples, 1):
        print(f"【サンプル {i}】{book[:40]}")
        print(f"  テキスト冒頭: {text[:80].strip()}...")
        print()

        for model in MODELS:
            t0 = time.perf_counter()
            names = extract_main_characters(text, model=model)
            elapsed = time.perf_counter() - t0
            times[model] += elapsed
            results[model].append(names)
            print(f"  {model:20s} → {names}  ({elapsed:.1f}s)")

        print()

    # サマリ
    print(f"{'=' * 60}")
    print("【合計時間】")
    for model in MODELS:
        avg = times[model] / len(samples)
        print(f"  {model:20s}: 合計 {times[model]:.1f}s  平均 {avg:.1f}s/ページ")

    print()
    print("【一致率】")
    match = sum(1 for i in range(len(samples)) if set(results[MODELS[0]][i]) == set(results[MODELS[1]][i]))
    print(f"  e4b と 12b が完全一致: {match}/{len(samples)} ページ")

    print()
    print("【差異があったページ】")
    any_diff = False
    for i, (book, _) in enumerate(samples):
        r0 = results[MODELS[0]][i]
        r1 = results[MODELS[1]][i]
        if set(r0) != set(r1):
            any_diff = True
            print(f"  サンプル {i + 1} ({book[:30]})")
            print(f"    e4b  → {r0}")
            print(f"    12b  → {r1}")
    if not any_diff:
        print("  なし（全サンプルで一致）")


if __name__ == "__main__":
    run_comparison()
