#!/bin/bash
# SQLite Online Backup APIでmeta2.db / novel.dbを、検証付きコピーでLanceDBを保存する。
# systemd timer または deploy_to_linux.sh から呼び出す。
set -euo pipefail

LABEL=${1:-$(date +%Y-%m-%d_%H%M%S)}

exec /opt/pic2pdf-viewer/backend/.venv/bin/python \
  -m tools.server_backup backup --label "$LABEL"
