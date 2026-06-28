#!/usr/bin/env bash
# Mac 開発用ワンコマンド起動スクリプト
# Backend (FastAPI :8766) と Frontend (Vite :5176) を同時起動し、
# Ctrl+C で両方まとめて停止する。
#
# 使い方:
#   ./scripts/start_dev.sh
# どこから実行しても OK（リポジトリルートを自動解決）。

set -euo pipefail

# --- リポジトリルートを解決 ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# --- Homebrew (uv / node) を PATH に通す（未ログインシェル対策） ---
if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi

BACKEND_PORT=8766
FRONTEND_PORT=5176

# --- 既存プロセスの掃除（ポート占有を防ぐ） ---
pkill -f "uvicorn main:app" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
sleep 1

PIDS=()

cleanup() {
  echo ""
  echo "==> 停止中..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  # 子プロセス（uvicorn / vite 実体）も確実に停止
  pkill -f "uvicorn main:app" 2>/dev/null || true
  pkill -f "vite" 2>/dev/null || true
  echo "==> 停止しました。"
}
trap cleanup INT TERM EXIT

echo "==> Backend  起動: http://localhost:${BACKEND_PORT}"
(
  cd "${ROOT_DIR}/backend"
  exec uv run uvicorn main:app --reload --port "${BACKEND_PORT}"
) 2>&1 | sed -u 's/^/[backend]  /' &
PIDS+=($!)

echo "==> Frontend 起動: http://localhost:${FRONTEND_PORT}"
(
  cd "${ROOT_DIR}/frontend"
  exec npm run dev
) 2>&1 | sed -u 's/^/[frontend] /' &
PIDS+=($!)

echo ""
echo "==> 起動しました。ブラウザで http://localhost:${FRONTEND_PORT} を開いてください。"
echo "==> 停止するには Ctrl+C を押してください。"
echo ""

# どちらかのプロセスが終了するまで待機
wait
