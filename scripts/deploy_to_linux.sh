#!/bin/bash
# Mac / Windows → Linux サーバーへアプリコードをデプロイするスクリプト
# 使い方: bash scripts/deploy_to_linux.sh
# 前提: Tailscale が起動していること、SSH 鍵認証が設定済みであること
#       サーバー側 amashio に NOPASSWD sudo (systemctl restart/status pic2pdf-viewer) 設定済み
set -e

# Homebrew の npm/node を PATH に通す（Mac、未ログインシェル対策。Windows では no-op）
if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi

LINUX_USER=amashio
LINUX_HOST=medaroserver
LINUX="${LINUX_USER}@${LINUX_HOST}"
APP_ROOT=/opt/pic2pdf-viewer
# リポジトリルートをスクリプト位置から自動解決（Mac / Windows Git Bash 両対応）
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ---- 1. フロントエンドをローカルでビルド ----
echo "=== [1/3] Frontend build ==="
cd "${SRC}/frontend"
# Generator API は Windows バックエンド（Tailscale 経由）へ向ける
VITE_GENERATE_API_URL=http://100.76.210.48:8090 npm run build
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

# ---- 3. デプロイ前バックアップ ----
echo "=== [3/4] Backing up meta2.db ==="
ssh "${LINUX}" "bash '${APP_ROOT}/deploy/backup-meta.sh' \$(date +%Y-%m-%d_%H%M%S)_pre-deploy"

# ---- 4. サービス再起動 ----
echo "=== [4/4] Restarting pic2pdf-viewer service ==="
ssh "${LINUX}" "sudo systemctl restart pic2pdf-viewer && sudo systemctl status pic2pdf-viewer"

echo ""
echo "Deploy complete: http://${LINUX_HOST}:8090"
