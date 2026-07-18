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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

input=$(cat)
mapfile -t file_paths < <(printf '%s' "$input" | python3 "$SCRIPT_DIR/hook_input.py" paths 2>/dev/null)

if [ "${#file_paths[@]}" -eq 0 ]; then
    exit 0
fi

# Pic2PDF_Viewer のレイアウト:
#   - backend/pyproject.toml + backend/uv.lock (uv 管理)
#   - frontend/package.json + frontend/package-lock.json (npm 管理)
needs_uv=false
needs_npm=false
for file_path in "${file_paths[@]}"; do
    normalized=$(echo "$file_path" | tr '\\' '/')
    case "/$normalized" in
        */backend/pyproject.toml|*/backend/uv.lock) needs_uv=true ;;
        */frontend/package.json|*/frontend/package-lock.json) needs_npm=true ;;
    esac
done

if $needs_uv && $needs_npm; then
    msg="依存変更を検出。次の作業前に: ルートで uv sync、frontend で npm install"
elif $needs_uv; then
    msg="バックエンドの依存変更を検出。次の作業前に: ルートで uv sync"
elif $needs_npm; then
    msg="フロントエンドの依存変更を検出。次の作業前に: cd frontend && npm install"
else
    exit 0
fi

cat <<EOF
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "$msg"}}
EOF
exit 0
