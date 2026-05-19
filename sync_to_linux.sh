#!/bin/bash
# Windows → Linux サーバーへ同期するスクリプト
# 使い方: bash sync_to_linux.sh [doujin|comic|novel|hitomi|db|all]
# 前提: Tailscale が起動していること、SSH 鍵認証が設定済みであること
set -e

LINUX_USER=amashio
LINUX_HOST=medaroserver
LINUX="${LINUX_USER}@${LINUX_HOST}"
DEST=/opt/pic2pdf-viewer/data
TARGET=${1:-all}

# データ格納場所
ONEDRIVE_DATA="/c/Users/amashio/OneDrive/61.tool/Pic2PDF"
DB_DATA="/d/61.tool/Pic2PDF_Viewer/backend/data"

# フル同期: サムネイル・小ファイル向け（毎回上書き）
sync_tar() {
    local src=$1 dst=$2
    if [[ ! -d "$src" ]]; then
        echo "Skip (not found): $src"
        return
    fi
    echo "Syncing: $src → $LINUX:$dst"
    tar czf - -C "$(dirname "$src")" "$(basename "$src")" \
        | ssh "$LINUX" "mkdir -p '$dst' && tar xzf - -C '$(dirname "$dst")'"
}

# 差分同期: images/ 向け（サーバーに存在しない or 空の書籍ディレクトリのみ転送）
sync_new_books() {
    local src=$1 dst=$2
    if [[ ! -d "$src" ]]; then
        echo "Skip (not found): $src"
        return
    fi
    echo "Syncing new books: $src → $LINUX:$dst"
    # サーバー側の「ファイルが1件以上あるディレクトリ」のみをスキップ対象にする
    # 空ディレクトリは再送する（前回の転送失敗でフォルダだけ残っているケース対応）
    local existing
    existing=$(ssh "$LINUX" "find '$dst' -maxdepth 2 -type f 2>/dev/null | sed 's|$dst/||' | cut -d/ -f1 | sort -u || true")
    local count=0
    for book_dir in "$src"/*/; do
        [[ -d "$book_dir" ]] || continue
        local book
        book=$(basename "$book_dir")
        if echo "$existing" | grep -Fqx "$book"; then
            echo "  Skip (exists): $book"
        else
            echo "  Sending: $book"
            tar czf - -C "$src" "$book" \
                | ssh "$LINUX" "tar xzf - -C '$dst'"
            count=$((count + 1))
        fi
    done
    echo "  Done: ${count} new book(s) transferred"
}

sync_db() {
    echo "Syncing DB..."
    tar czf - -C "${DB_DATA}" meta.db novel_db \
        | ssh "$LINUX" "tar xzf - -C '${DEST}/'"
}

sync_hitomi() {
    echo "Syncing hitomi..."
    tar czf - -C "${ONEDRIVE_DATA}" hitomi \
        | ssh "$LINUX" "tar xzf - -C '${DEST}/'"
}

if [[ "$TARGET" == "doujin" || "$TARGET" == "all" ]]; then
    sync_tar      "${ONEDRIVE_DATA}/doujin/thumbnails" "${DEST}/doujin/thumbnails"
    sync_new_books "${ONEDRIVE_DATA}/doujin/images"    "${DEST}/doujin/images"
fi

if [[ "$TARGET" == "comic" || "$TARGET" == "all" ]]; then
    sync_tar      "${ONEDRIVE_DATA}/comic/thumbnails" "${DEST}/comic/thumbnails"
    sync_new_books "${ONEDRIVE_DATA}/comic/images"    "${DEST}/comic/images"
fi

if [[ "$TARGET" == "novel" || "$TARGET" == "all" ]]; then
    sync_tar      "${ONEDRIVE_DATA}/kindle_novel/thumbnails" "${DEST}/kindle_novel/thumbnails"
    sync_new_books "${ONEDRIVE_DATA}/kindle_novel/images"    "${DEST}/kindle_novel/images"
fi

if [[ "$TARGET" == "hitomi" || "$TARGET" == "all" ]]; then
    sync_hitomi
fi

if [[ "$TARGET" == "db" ]]; then
    sync_db
fi

echo ""
echo "Sync complete: $TARGET"
