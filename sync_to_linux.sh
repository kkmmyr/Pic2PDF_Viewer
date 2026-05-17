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

# Windows の Git Bash / WSL でのパス解決用
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/backend/data"

sync_dir() {
    local src=$1 dst=$2
    echo "Syncing: $src → $LINUX:$dst"
    rsync -avz --progress "$src/" "${LINUX}:${dst}/"
}

sync_db() {
    echo "Syncing DB..."
    rsync -avz --progress "${DATA_DIR}/meta.db"   "${LINUX}:${DEST}/"
    rsync -avz --progress "${DATA_DIR}/novel_db/"  "${LINUX}:${DEST}/novel_db/"
}

if [[ "$TARGET" == "doujin" || "$TARGET" == "all" ]]; then
    sync_dir "${DATA_DIR}/doujin/pdfs_compressed" "${DEST}/doujin/pdfs_compressed"
    sync_dir "${DATA_DIR}/doujin/thumbnails"      "${DEST}/doujin/thumbnails"
fi

if [[ "$TARGET" == "comic" || "$TARGET" == "all" ]]; then
    sync_dir "${DATA_DIR}/comic/pdfs"       "${DEST}/comic/pdfs"
    sync_dir "${DATA_DIR}/comic/thumbnails" "${DEST}/comic/thumbnails"
fi

if [[ "$TARGET" == "novel" || "$TARGET" == "all" ]]; then
    sync_dir "${DATA_DIR}/novel/pdfs"       "${DEST}/novel/pdfs"
    sync_dir "${DATA_DIR}/novel/thumbnails" "${DEST}/novel/thumbnails"
fi

sync_db

echo ""
echo "Sync complete: $TARGET"
