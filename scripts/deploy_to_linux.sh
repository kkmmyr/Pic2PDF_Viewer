#!/bin/bash
# Mac / Windows → Linux サーバーへアプリコードをデプロイするスクリプト
# 使い方: bash scripts/deploy_to_linux.sh
# 前提: Tailscale が起動していること、SSH 鍵認証が設定済みであること
#       サーバー側 amashio に NOPASSWD sudo (systemctl restart/status pic2pdf-viewer) 設定済み
set -euo pipefail

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
DEPLOY_GENERATION="$(date +%Y%m%d%H%M%S)-$$"
NEXT_BACKEND="${APP_ROOT}/backend-${DEPLOY_GENERATION}"
NEXT_COMMON="${APP_ROOT}/common/llm-${DEPLOY_GENERATION}"
STAGED_WORKSPACE="${APP_ROOT}/.deploy-workspace-${DEPLOY_GENERATION}"

# ---- 1. フロントエンドをローカルでビルド ----
echo "=== [1/3] Frontend build ==="
cd "${SRC}/frontend"
# Generator API は Windows バックエンド（Tailscale 経由）へ向ける
VITE_GENERATE_API_URL=http://100.76.210.48:8090 npm run build
cd "${SRC}"

# ---- 2. workspace・コードをサーバーへ転送 ----
echo "=== [2/3] Syncing code to ${LINUX}:${APP_ROOT} ==="

ssh "${LINUX}" "set -e; \
  test ! -e '${NEXT_BACKEND}' && test ! -L '${NEXT_BACKEND}'; \
  test ! -e '${NEXT_COMMON}' && test ! -L '${NEXT_COMMON}'; \
  test ! -e '${STAGED_WORKSPACE}' && test ! -L '${STAGED_WORKSPACE}'; \
  mkdir -p '${NEXT_BACKEND}' '${NEXT_COMMON}' '${STAGED_WORKSPACE}/common' \
    '${STAGED_WORKSPACE}/kindle-pdf'"

# uv workspace root（本番dependencyの正本）
tar czf - -C "${SRC}" pyproject.toml uv.lock \
    | ssh "${LINUX}" "mkdir -p '${APP_ROOT}' && tar xzf - -C '${APP_ROOT}'"
tar czf - -C "${SRC}" pyproject.toml uv.lock \
    | ssh "${LINUX}" "tar xzf - -C '${STAGED_WORKSPACE}'"
tar czf - -C "${SRC}/kindle-pdf" pyproject.toml \
    | ssh "${LINUX}" "tar xzf - -C '${STAGED_WORKSPACE}/kindle-pdf'"

# backend (Python ソース・設定。.venv / data / __pycache__ は除外)
# -prune でディレクトリごとスキップ（Git Bash では -not -path が効かないため）
(cd "${SRC}/backend" && find . \
    \( -name '.venv*' -o -name 'data' -o -name 'complete' -o -name '__pycache__' \
       -o -name 'htmlcov' -o -name '.pytest_cache' -o -name 'logs' -o -name 'input' \) -prune \
    -o -type f -not -name '*.pyc' -print \
    | tar czf - -C "${SRC}/backend" --files-from=-) \
    | ssh "${LINUX}" "tar xzf - -C '${NEXT_BACKEND}'"

# qwen-common workspace member（backendからeditable dependencyとして参照）
(cd "${SRC}/common/llm" && find . \
    \( -name '.venv*' -o -name '__pycache__' -o -name '.pytest_cache' \
       -o -name '*.egg-info' \) -prune \
    -o -type f -not -name '*.pyc' -print \
    | tar czf - -C "${SRC}/common/llm" --files-from=-) \
    | ssh "${LINUX}" "tar xzf - -C '${NEXT_COMMON}'"

ssh "${LINUX}" "ln -s '${NEXT_BACKEND}' '${STAGED_WORKSPACE}/backend' && \
  ln -s '${NEXT_COMMON}' '${STAGED_WORKSPACE}/common/llm'"

# frontend/dist (ビルド成果物のみ)
tar czf - -C "${SRC}/frontend" dist \
    | ssh "${LINUX}" "tar xzf - -C '${APP_ROOT}/frontend'"

# deploy/ (systemd / nginx 設定)
tar czf - -C "${SRC}" deploy \
    | ssh "${LINUX}" "tar xzf - -C '${APP_ROOT}'"

# ---- 3. 検証付きbackup・世代venv構築・atomic切替 ----
echo "=== [3/3] Activating locked backend environment ==="
DEPLOY_LABEL="$(date +%Y-%m-%d_%H%M%S)_pre-deploy"
ssh "${LINUX}" "bash '${APP_ROOT}/deploy/activate-backend.sh' \
  '${DEPLOY_LABEL}' '${NEXT_BACKEND}' '${NEXT_COMMON}' '${STAGED_WORKSPACE}'"

echo ""
echo "Deploy complete: http://${LINUX_HOST}:8090"
echo "Backend generation: ${NEXT_BACKEND}"
