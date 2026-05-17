#!/bin/bash
# Windows → Linux サーバーへ差分 push するスクリプト
# 使い方: bash sync_to_linux.sh [doujin|comic|novel|all]
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

sync_db() {
    echo "Syncing DB..."
    tar czf - -C "${DB_DATA}" meta.db novel_db \
        | ssh "$LINUX" "tar xzf - -C '${DEST}/'"
}

if [[ "$TARGET" == "doujin" || "$TARGET" == "all" ]]; then
    sync_tar "${ONEDRIVE_DATA}/doujin/thumbnails" "${DEST}/doujin/thumbnails"
    sync_tar "${ONEDRIVE_DATA}/doujin/images"     "${DEST}/doujin/images"
fi

if [[ "$TARGET" == "comic" || "$TARGET" == "all" ]]; then
    sync_tar "${ONEDRIVE_DATA}/comic/thumbnails" "${DEST}/comic/thumbnails"
    sync_tar "${ONEDRIVE_DATA}/comic/images"     "${DEST}/comic/images"
fi

if [[ "$TARGET" == "novel" || "$TARGET" == "all" ]]; then
    sync_tar "${ONEDRIVE_DATA}/kindle_novel/thumbnails" "${DEST}/kindle_novel/thumbnails"
    sync_tar "${ONEDRIVE_DATA}/kindle_novel/images"     "${DEST}/kindle_novel/images"
fi

sync_db

echo ""
echo "Sync complete: $TARGET"
