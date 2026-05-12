#!/bin/bash
# PostToolUse hook for Edit/Write — docs/*.md 編集後に mkdocs build を実行する。
# CLAUDE.md の運用ルール「Markdown 編集後は mkdocs build で HTML 反映が必要」を自動化。
# ビルド失敗は警告として additionalContext で通知（ブロックはしない）。
#
# Reads tool input as JSON from stdin.

set -e

# Hook script の location から project root を解決（CWD 非依存）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

input=$(cat)
file_path=$(echo "$input" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print((d.get('tool_input') or {}).get('file_path') or '')
" 2>/dev/null || true)

if [ -z "$file_path" ]; then
    exit 0
fi

normalized=$(echo "$file_path" | tr '\\' '/')

# docs/ 配下の .md 編集だけが対象
case "$normalized" in
    */docs/*.md) ;;
    *) exit 0 ;;
esac

# mkdocs.yml が無ければスキップ（ビルド対象外プロジェクト）
if [ ! -f "$PROJECT_ROOT/mkdocs.yml" ]; then
    exit 0
fi

# mkdocs コマンドの解決：PATH 上 or uv tool 配置先（~/.local/bin）
MKDOCS_BIN=""
if command -v mkdocs >/dev/null 2>&1; then
    MKDOCS_BIN="mkdocs"
elif [ -x "$HOME/.local/bin/mkdocs" ]; then
    MKDOCS_BIN="$HOME/.local/bin/mkdocs"
fi

if [ -z "$MKDOCS_BIN" ]; then
    msg="mkdocs が PATH に見つかりません。HTML 再ビルドをスキップ。'uv tool install mkdocs --with mkdocs-material --with mkdocs-mermaid2-plugin' を実行してください。"
    msg_json=$(printf '%s' "$msg" | python3 -c "import json,sys; print(json.dumps(sys.stdin.read(), ensure_ascii=False))")
    cat <<EOF
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": $msg_json}}
EOF
    exit 0
fi

# ビルド実行（--dirty で増分ビルド：Vite dev が site_dir のハッシュ付き asset を握っていても PermissionError を回避）
build_failed=0
output=$(cd "$PROJECT_ROOT" && "$MKDOCS_BIN" build --dirty --quiet 2>&1) || build_failed=1

if [ "$build_failed" -eq 1 ]; then
    msg=$(printf 'mkdocs build に失敗しました。docs/ 編集を確認してください:\n%s' "$output")
    msg_json=$(printf '%s' "$msg" | python3 -c "import json,sys; print(json.dumps(sys.stdin.read(), ensure_ascii=False))")
    cat <<EOF
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": $msg_json}}
EOF
fi

exit 0
