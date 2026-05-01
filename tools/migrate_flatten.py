"""
フォルダ -> フラット移行スクリプト

プリンセスコネクト/ と Voiceloid/ 内の PDF をルート直下に移動し、
フォルダ名を tags に自動付与する。meta.json のキーも更新する。

実行: cd backend && uv run python ../tools/migrate_flatten.py [--dry-run]
"""
import os
import sys

# Windows cp932 端末で日本語ファイル名の表示が文字化けするのを防ぐ
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../backend")

from config import get_dirs_by_source
from services.file_manager import FileManager
from services.meta_store import load_meta, save_meta, get_lock

SOURCE = "generated"
FOLDER_TAGS: dict[str, str] = {
    "プリンセスコネクト": "プリンセスコネクト",
    "Voiceloid": "Voiceloid",
}

def main(dry_run: bool) -> None:
    dirs = get_dirs_by_source(SOURCE)
    pdf_root = dirs["pdf"]

    # 衝突チェック
    root_pdfs = {f for f in os.listdir(pdf_root) if f.lower().endswith(".pdf")}
    conflicts: list[str] = []
    for folder in FOLDER_TAGS:
        folder_dir = os.path.join(pdf_root, folder)
        if not os.path.exists(folder_dir):
            continue
        for f in os.listdir(folder_dir):
            if f.lower().endswith(".pdf") and f in root_pdfs:
                conflicts.append(f"{folder}/{f}")

    if conflicts:
        print("[ERROR] 衝突ファイルが存在するため中断します:")
        for c in conflicts:
            print(f"  {c}")
        sys.exit(1)

    if dry_run:
        print("=== DRY RUN（実際の変更なし）===\n")

    total_moved = 0

    # ファイル移動（meta 更新前に全移動）
    for folder, tag in FOLDER_TAGS.items():
        folder_dir = os.path.join(pdf_root, folder)
        if not os.path.exists(folder_dir):
            print(f"スキップ（フォルダなし）: {folder}")
            continue

        pdfs = sorted(f for f in os.listdir(folder_dir) if f.lower().endswith(".pdf"))
        print(f"\n[{folder}]: {len(pdfs)} 件を移行")
        for pdf_name in pdfs:
            prefix = "[DRY] " if dry_run else ""
            print(f"  {prefix}{folder}/{pdf_name} -> {pdf_name}  (tag: {tag})")
            if not dry_run:
                FileManager.move_with_assets(pdf_name, folder, "", dirs)
            total_moved += 1

    if total_moved == 0:
        print("移行対象なし。終了します。")
        return

    if dry_run:
        print(f"\n合計 {total_moved} 件を移動予定（変更なし）")
        return

    # meta.json を一括更新
    with get_lock(SOURCE):
        meta = load_meta(SOURCE)
        for folder, tag in FOLDER_TAGS.items():
            for old_key in list(meta.keys()):
                prefix = folder + "/"
                if not old_key.startswith(prefix):
                    continue
                new_key = old_key[len(prefix):]
                entry = meta.pop(old_key)
                existing_tags: list[str] = entry.get("tags") or []
                if tag not in existing_tags:
                    existing_tags = existing_tags + [tag]
                entry["tags"] = existing_tags
                meta[new_key] = entry
        save_meta(SOURCE, meta)
    print("\n[OK] meta.json を更新しました")

    # 空フォルダを削除（PDF・サムネイル・画像フォルダ）
    for folder in FOLDER_TAGS:
        for base_dir in (dirs["pdf"], dirs["thumb"], dirs["img"]):
            folder_path = os.path.join(base_dir, folder)
            if not os.path.exists(folder_path):
                continue
            remaining = [f for f in os.listdir(folder_path) if not f.startswith(".")]
            if remaining:
                print(f"[WARN] フォルダが空でないため削除しません: {folder_path}")
                for r in remaining:
                    print(f"  残存: {r}")
            else:
                os.rmdir(folder_path)
                print(f"[DEL] 空フォルダ削除: {folder_path}")

    # 謎の子など残った空フォルダも掃除（PDF 0 件）
    for item in os.listdir(dirs["pdf"]):
        full = os.path.join(dirs["pdf"], item)
        if os.path.isdir(full) and not any(f.lower().endswith(".pdf") for f in os.listdir(full)):
            remaining = [f for f in os.listdir(full) if not f.startswith(".")]
            if not remaining:
                os.rmdir(full)
                print(f"[DEL] 空フォルダ削除（残存）: {full}")

    print(f"\n[DONE] {total_moved} 件を移行しました。")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run)
