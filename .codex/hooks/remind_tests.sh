#!/bin/bash
# PostToolUse hook for Edit/Write.
# Passive reminder: only nags for substantive backend (.py) or frontend (.ts/.tsx/.js/.jsx) source changes.
# Skips: configs, tests, docs, agent config, small diffs, comment-only changes.
#
# Reads tool input as JSON from stdin.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

input=$(cat)
mapfile -t file_paths < <(printf '%s' "$input" | python3 "$SCRIPT_DIR/hook_input.py" paths 2>/dev/null)
added_text=$(printf '%s' "$input" | python3 "$SCRIPT_DIR/hook_input.py" added-text 2>/dev/null || true)

if [ "${#file_paths[@]}" -eq 0 ]; then
    exit 0
fi

# Skip small diffs
added_lines=$(printf '%s\n' "$added_text" | wc -l | tr -d ' ')
if [ "$added_lines" -lt 10 ]; then
    exit 0
fi

# Skip if no function/class/endpoint definition added
if ! echo "$added_text" | grep -qE '(def |class |function |const [A-Za-z_]+ = |@router\.|@app\.|export (function|const|class))'; then
    exit 0
fi

has_backend=false
has_frontend=false
for file_path in "${file_paths[@]}"; do
    normalized=$(echo "$file_path" | tr '\\' '/')
    case "$normalized" in
        */docs/*|*/.claude/*|*/.codex/*|*/.agents/*) continue ;;
        */test/*|*/tests/*|*/__tests__/*|*.test.*|*.spec.*) continue ;;
        *.md|*.json|*.toml|*.lock|*.txt|*.bat|*.sh|*.yml|*.yaml|*.env|*.ini|*.cfg|*.gitignore|*.tsbuildinfo) continue ;;
    esac
    case "/$normalized" in
        */backend/*.py) has_backend=true ;;
        */frontend/src/*.ts|*/frontend/src/*.tsx|*/frontend/src/*.js|*/frontend/src/*.jsx) has_frontend=true ;;
    esac
done

if $has_backend && $has_frontend; then
    msg="バックエンド・フロントエンド変更を検出。pytest、tsc -b、vitest の実行を検討してください。"
elif $has_backend; then
    msg="バックエンド変更を検出。テストを検討してください: cd backend && uv run pytest"
elif $has_frontend; then
    msg="フロントエンド変更を検出。型チェック + テストを検討してください: cd frontend && npx tsc -b && npm run test -- --run"
else
    exit 0
fi

cat <<EOF
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "$msg"}}
EOF
exit 0
