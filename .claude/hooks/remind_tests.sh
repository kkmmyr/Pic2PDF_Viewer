#!/bin/bash
# PostToolUse hook for Edit/Write.
# Passive reminder: only nags for substantive backend (.py) or frontend (.ts/.tsx/.js/.jsx) source changes.
# Skips: configs, tests, docs, .claude, small diffs, comment-only changes.
#
# Reads tool input as JSON from stdin.

set -e

input=$(cat)

# Parse JSON via Python (handles Windows path backslash-escaping correctly)
parsed=$(echo "$input" | python3 -c "
import json, sys
d = json.load(sys.stdin)
ti = d.get('tool_input') or {}
fp  = ti.get('file_path', '')
os_ = ti.get('old_string', '')
ns  = ti.get('new_string', '')
print(fp)
print(os_.count('\n'))
print(ns.count('\n'))
print(ns)
" 2>/dev/null) || true

if [ -z "$parsed" ]; then
    exit 0
fi

file_path=$(echo "$parsed" | sed -n '1p')
if [ -z "$file_path" ]; then
    exit 0
fi

old_lines=$(echo "$parsed" | sed -n '2p')
new_lines=$(echo "$parsed" | sed -n '3p')
new_string=$(echo "$parsed" | tail -n +4)

normalized=$(echo "$file_path" | tr '\\' '/')

# Skip non-source files / tests / docs / configs
case "$normalized" in
    */docs/*|*/.claude/*) exit 0 ;;
    */test/*|*/tests/*|*/__tests__/*|*.test.*|*.spec.*) exit 0 ;;
    *.md|*.json|*.toml|*.lock|*.txt|*.bat|*.sh|*.yml|*.yaml|*.env|*.ini|*.cfg|*.gitignore|*.tsbuildinfo) exit 0 ;;
esac

# Only handle source files
case "$normalized" in
    *.py|*.ts|*.tsx|*.js|*.jsx) ;;
    *) exit 0 ;;
esac

# Estimate diff size by line count
diff_lines=$((new_lines > old_lines ? new_lines - old_lines : old_lines - new_lines))

# Skip small diffs
if [ "$diff_lines" -lt 10 ]; then
    exit 0
fi

# Skip if no function/class/endpoint definition added
if ! echo "$new_string" | grep -qE '(def |class |function |const [A-Za-z_]+ = |@router\.|@app\.|export (function|const|class))'; then
    exit 0
fi

# Substantive change to source — emit a passive reminder
case "$normalized" in
    *.py)   msg="バックエンド変更を検出。テストを検討してください: cd backend && uv run pytest" ;;
    *.ts|*.tsx|*.js|*.jsx)
            msg="フロントエンド変更を検出。型チェック + テストを検討してください: cd frontend && npx tsc --noEmit && npm run test -- --run" ;;
    *)      msg="ソース変更を検出。テストを検討してください。" ;;
esac

cat <<EOF
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "$msg"}}
EOF
exit 0
