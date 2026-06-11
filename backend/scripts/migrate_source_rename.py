"""ソース値リネーム移行スクリプト。

kindle  → comic、generated(main) → doujin のデータディレクトリ・メタ/ジャンル JSON を
物理的にリネームする一回限りの移行スクリプト。

使用例（backend ディレクトリ内で実行）:

    cd backend
    uv run python scripts/migrate_source_rename.py --dry-run   # 計画表示
    uv run python scripts/migrate_source_rename.py --execute   # 実行

べき等性: すでにリネーム済みのパスは skip する。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_DATA_DIR = _BACKEND_DIR / "data"

RENAMES: list[tuple[Path, Path]] = [
    (_DATA_DIR / "kindle", _DATA_DIR / "comic"),
    (_DATA_DIR / "main", _DATA_DIR / "doujin"),
    (_DATA_DIR / "meta" / "kindle", _DATA_DIR / "meta" / "comic"),
    (_DATA_DIR / "meta" / "generated", _DATA_DIR / "meta" / "doujin"),
    (_DATA_DIR / "genres" / "kindle.json", _DATA_DIR / "genres" / "comic.json"),
    (_DATA_DIR / "genres" / "generated.json", _DATA_DIR / "genres" / "doujin.json"),
]

MARKER = _DATA_DIR / ".migration_source_rename_done"


def _print_plan() -> None:
    print("=== 移行計画 ===")
    for src, dst in RENAMES:
        exists = src.exists()
        dst_exists = dst.exists()
        status = "SKIP (src なし)" if not exists and not dst_exists else "SKIP (dst 既存)" if dst_exists else "RENAME"
        print(f"  [{status}] {src.relative_to(_BACKEND_DIR)}  →  {dst.relative_to(_BACKEND_DIR)}")


def _execute() -> None:
    if MARKER.exists():
        print("マーカーファイルが存在します。既に移行済みです。")
        print(f"  {MARKER}")
        sys.exit(0)

    errors: list[str] = []
    for src, dst in RENAMES:
        if not src.exists():
            if dst.exists():
                print(f"  SKIP (dst 既存): {src.name}")
            else:
                print(f"  SKIP (src なし): {src.name}")
            continue
        if dst.exists():
            print(f"  SKIP (dst 既存): {dst.name}")
            continue
        try:
            src.rename(dst)
            print(f"  OK: {src.relative_to(_BACKEND_DIR)}  →  {dst.relative_to(_BACKEND_DIR)}")
        except OSError as e:
            errors.append(f"  ERROR: {src} → {dst}: {e}")

    if errors:
        print("\n以下のエラーが発生しました:")
        for msg in errors:
            print(msg)
        sys.exit(1)

    MARKER.write_text("source rename migration done\n", encoding="utf-8")
    print(f"\n完了。マーカー書き込み: {MARKER.relative_to(_BACKEND_DIR)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="source 値リネーム移行スクリプト")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="移行計画を表示するだけ（変更なし）")
    group.add_argument("--execute", action="store_true", help="実際に移行を実行する")
    args = parser.parse_args()

    print(f"データディレクトリ: {_DATA_DIR}\n")
    if args.dry_run:
        _print_plan()
    else:
        _print_plan()
        print()
        _execute()


if __name__ == "__main__":
    main()
