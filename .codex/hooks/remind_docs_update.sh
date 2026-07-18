#!/bin/bash
# PreToolUse hook for Edit/Write — passive reminder.
# 設計書（docs/）の事前更新を促すが、ブロックはしない（advisory）。
# 軽微な編集（typo・コメント追加・テスト調整等）まで止めると不便なため、
# 強制ではなくモデルへのヒントとして additionalContext で追加する。
#
# Reads tool input as JSON from stdin.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${HOOK_PROJECT_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

input=$(cat)
mapfile -t file_paths < <(printf '%s' "$input" | python3 "$SCRIPT_DIR/hook_input.py" paths 2>/dev/null)

if [ "${#file_paths[@]}" -eq 0 ]; then
    exit 0
fi

# Step 1: 対象となるソースファイルがあるか
has_source=false
for file_path in "${file_paths[@]}"; do
    normalized=$(echo "$file_path" | tr '\\' '/')
    case "$normalized" in
        */docs/*|*/.claude/*|*/.codex/*|*/.agents/*) continue ;;
        *.md|*.json|*.toml|*.lock|*.txt|*.bat|*.sh|*.yml|*.yaml|*.env|*.ini|*.cfg|*.gitignore|*.tsbuildinfo) continue ;;
        */test/*|*/tests/*|*/__tests__/*|*.test.*|*.spec.*) continue ;;
        *.py|*.ts|*.tsx|*.js|*.jsx) has_source=true ;;
    esac
done
$has_source || exit 0

# Step 2: docs/ に既に未コミットの差分があれば「設計書は更新済み」と解釈してスキップ
docs_status=$(git -C "$PROJECT_ROOT" status --porcelain docs/ 2>/dev/null || true)
if [ -n "$docs_status" ]; then
    exit 0
fi

# Step 2.5: 同一 HEAD で既に一度通知済みならスキップ（繰り返し発火防止）
# コミット後に HEAD が変わると自動リセットされる。
head_hash=$(git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null || echo "no-repo")
marker_file="/tmp/remind_docs_${head_hash}.marker"
if [ -f "$marker_file" ]; then
    exit 0
fi
touch "$marker_file"

# Step 3: ソース変更で docs/ 未更新 → advisory として additionalContext を追加
cat <<'EOF'
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "設計の意図に関わる変更なら、この編集の前に docs/ 更新 → 変更履歴.md の順序を先行させてください（手順・スキップ条件: AGENTS.md「タスク完了後の必須アクション」/ docs-workflow skill）。"}}
EOF
exit 0
