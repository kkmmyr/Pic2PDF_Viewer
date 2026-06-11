#!/bin/bash
# meta2.db をバックアップから復元する。
# 使い方:
#   bash restore_meta.sh            # バックアップ一覧を表示
#   bash restore_meta.sh 2026-05-27 # 指定日のバックアップで復元
# 前提: Tailscale が起動していること、SSH 鍵認証が設定済みであること

LINUX_USER=amashio
LINUX_HOST=medaroserver
LINUX="${LINUX_USER}@${LINUX_HOST}"
BACKUP_DIR=/opt/pic2pdf-viewer/data/backups
META_DB=/opt/pic2pdf-viewer/data/meta2.db

if [[ -z "$1" ]]; then
    echo "=== 利用可能なバックアップ ==="
    ssh "${LINUX}" "ls -lt '${BACKUP_DIR}'/meta2_*.db 2>/dev/null | awk '{print \$NF}' | sed 's|.*/||' || echo '(バックアップなし)'"
    echo ""
    echo "復元するには: bash restore_meta.sh <ラベル>"
    echo "例: bash restore_meta.sh 2026-05-27"
    exit 0
fi

LABEL="$1"
BACKUP_FILE="${BACKUP_DIR}/meta2_${LABEL}.db"

echo "=== 復元確認 ==="
echo "  バックアップ: ${BACKUP_FILE}"
echo "  復元先:       ${META_DB}"
read -p "続行しますか？ [y/N] " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "キャンセルしました。"
    exit 0
fi

ssh "${LINUX}" "
    if [[ ! -f '${BACKUP_FILE}' ]]; then
        echo 'ERROR: バックアップが見つかりません: ${BACKUP_FILE}'
        exit 1
    fi
    # 復元前に現在のDBを緊急バックアップ
    cp '${META_DB}' '${BACKUP_DIR}/meta2_before-restore_\$(date +%Y-%m-%d_%H%M%S).db'
    cp '${BACKUP_FILE}' '${META_DB}'
    echo '復元完了: ${BACKUP_FILE} → ${META_DB}'
"

echo ""
echo "サービスを再起動します..."
ssh "${LINUX}" "sudo systemctl restart pic2pdf-viewer"
echo "完了しました。"
