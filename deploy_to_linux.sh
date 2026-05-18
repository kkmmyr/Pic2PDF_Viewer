#!/bin/bash
# Windows → Linux サーバーへアプリコードをデプロイするスクリプト
# 使い方: bash deploy_to_linux.sh
# 前提: Tailscale が起動していること、SSH 鍵認証が設定済みであること
set -e

LINUX_USER=amashio
LINUX_HOST=medaroserver
LINUX="${LINUX_USER}@${LINUX_HOST}"
APP_ROOT=/opt/pic2pdf-viewer
SRC="/d/61.tool/Pic2PDF_Viewer"

# ---- 1. フロントエンドをローカルでビルド ----
echo "=== [1/3] Frontend build ==="
cd "${SRC}/frontend"
npm run build
cd "${SRC}"

# ---- 2. コードをサーバーへ転送 ----
echo "=== [2/3] Syncing code to ${LINUX}:${APP_ROOT} ==="

# backend (Python ソース・設定。.venv / data / __pycache__ は除外)
# -prune でディレクトリごとスキップ（Git Bash では -not -path が効かないため）
(cd "${SRC}/backend" && find . \
    \( -name '.venv' -o -name 'data' -o -name 'complete' -o -name '__pycache__' \
       -o -name 'htmlcov' -o -name '.pytest_cache' -o -name 'logs' -o -name 'input' \) -prune \
    -o -type f -not -name '*.pyc' -print \
    | tar czf - -C "${SRC}/backend" --files-from=-) \
    | ssh "${LINUX}" "tar xzf - -C '${APP_ROOT}/backend'"

# frontend/dist (ビルド成果物のみ)
tar czf - -C "${SRC}/frontend" dist \
    | ssh "${LINUX}" "tar xzf - -C '${APP_ROOT}/frontend'"

# deploy/ (systemd / nginx 設定)
tar czf - -C "${SRC}" deploy \
    | ssh "${LINUX}" "tar xzf - -C '${APP_ROOT}'"

# ---- 3. サービス再起動 ----
echo "=== [3/3] Restarting pic2pdf-viewer service ==="
ssh "${LINUX}" "sudo systemctl restart pic2pdf-viewer && sudo systemctl status pic2pdf-viewer"

echo ""
echo "Deploy complete: http://${LINUX_HOST}:8090"
