#!/bin/bash
# meta2.db を日次バックアップする。14日分を保持。
# systemd timer または deploy_to_linux.sh から呼び出す。
set -e

META_DB=/opt/pic2pdf-viewer/data/meta2.db
BACKUP_DIR=/opt/pic2pdf-viewer/data/backups
LABEL=${1:-$(date +%Y-%m-%d)}

mkdir -p "$BACKUP_DIR"

if [[ ! -f "$META_DB" ]]; then
    echo "[backup-meta] meta2.db not found: $META_DB"
    exit 1
fi

DEST="$BACKUP_DIR/meta2_${LABEL}.db"
cp "$META_DB" "$DEST"
echo "[backup-meta] saved: $DEST"

# 14日より古いバックアップを削除
find "$BACKUP_DIR" -name "meta2_*.db" -mtime +14 -delete
echo "[backup-meta] old backups purged (>14 days)"
