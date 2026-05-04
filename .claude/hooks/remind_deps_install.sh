#!/bin/bash
# PostToolUse hook for Edit/Write on dependency manifest files.
# 依存マニフェスト（pyproject.toml / uv.lock / package.json / package-lock.json /
# requirements.txt / Pipfile / Pipfile.lock 等）の編集を検知し、
# `uv sync` / `npm install` 等の実行を passive に提案する。
#
# プロジェクトのレイアウトに応じて case ブロックの path / msg を書き換えること。
# 該当ブロック全体が不要なら settings.json から登録を外す。
#
# Reads tool input as JSON from stdin.

set -e

input=$(cat)
file_path=$(echo "$input" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('file_path',''))" 2>/dev/null || true)

if [ -z "$file_path" ]; then
    exit 0
fi

normalized=$(echo "$file_path" | tr '\\' '/')

# Pic2PDF_Viewer のレイアウト:
#   - backend/pyproject.toml + backend/uv.lock (uv 管理)
#   - frontend/package.json + frontend/package-lock.json (npm 管理)
case "$normalized" in
    # ── Python (uv) ──
    */backend/pyproject.toml|*/backend/uv.lock)
        msg="バックエンドの依存変更を検出。次の作業前に: cd backend && uv sync"
        ;;
    # ── Node (npm) ──
    */frontend/package.json|*/frontend/package-lock.json)
        msg="フロントエンドの依存変更を検出。次の作業前に: cd frontend && npm install"
        ;;
    *)
        exit 0
        ;;
esac

cat <<EOF
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "$msg"}}
EOF
exit 0
