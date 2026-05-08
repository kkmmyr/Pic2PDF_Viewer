"""
meta.json から tags フィールドを完全削除するマイグレーション。

タグ手入力機能の撤去（2026-05-08）に伴い、`backend/data/meta/{generated,kindle,novel}/meta.json`
の各エントリから `tags` フィールドを削除する。撤去後は再度書き込まれることはない。

実行:
    cd backend
    uv run python ../tools/migrate_remove_tags.py --dry-run    # 削除件数を確認
    uv run python ../tools/migrate_remove_tags.py --apply      # 実行
"""

import argparse
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../backend")

from services.meta_store import get_lock, load_meta, save_meta

SOURCES = ("generated", "kindle", "novel")


def remove_tags_from_source(source: str, apply: bool) -> tuple[int, int]:
    """指定ソースの meta.json から tags を削除。

    Returns:
        (entries_with_tags, total_entries)
    """
    with get_lock(source):
        meta = load_meta(source)
        total = len(meta)
        affected = sum(1 for entry in meta.values() if "tags" in entry)

        if affected == 0:
            return 0, total

        for entry in meta.values():
            entry.pop("tags", None)

        if apply:
            save_meta(source, meta)

    return affected, total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="削除件数のみ表示（変更なし）")
    group.add_argument("--apply", action="store_true", help="実際に meta.json を書き換える")
    args = parser.parse_args()

    apply = args.apply
    mode_label = "APPLY" if apply else "DRY RUN"
    print(f"=== {mode_label}: タグフィールド削除 ===\n")

    grand_total_affected = 0
    grand_total_entries = 0

    for source in SOURCES:
        try:
            affected, total = remove_tags_from_source(source, apply)
        except FileNotFoundError:
            print(f"[{source}] meta.json が存在しないためスキップ")
            continue

        grand_total_affected += affected
        grand_total_entries += total
        print(f"[{source}] {affected} / {total} エントリから tags を削除")

    print()
    print(f"合計: {grand_total_affected} / {grand_total_entries} エントリ")
    if apply:
        print("\n[DONE] meta.json を更新しました。")
    else:
        print("\n[DRY RUN] 変更は適用していません。--apply で実行してください。")


if __name__ == "__main__":
    main()
