#!/bin/bash
# PostToolUse hook for Edit/Write.
# Passive reminder: only nags for substantive backend (.py) or frontend (.ts/.tsx/.js/.jsx) source changes.
# Skips: configs, tests, docs, .claude, small diffs, comment-only changes.
#
# Reads tool input as JSON from stdin.

set -e

input=$(cat)
file_path=$(echo "$input" | grep -oE '"file_path"\s*:\s*"[^"]+"' | head -1 | sed -E 's/.*"file_path"\s*:\s*"([^"]+)".*/\1/')
old_string=$(echo "$input" | grep -oE '"old_string"\s*:\s*"[^"]*"' | head -1 | sed -E 's/.*"old_string"\s*:\s*"(.*)".*/\1/')
new_string=$(echo "$input" | grep -oE '"new_string"\s*:\s*"[^"]*"' | head -1 | sed -E 's/.*"new_string"\s*:\s*"(.*)".*/\1/')

if [ -z "$file_path" ]; then
    exit 0
fi

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

# Estimate diff size by line count of new_string vs old_string
old_lines=$(echo -n "$old_string" | grep -c '\\n' || echo 0)
new_lines=$(echo -n "$new_string" | grep -c '\\n' || echo 0)
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
# .py → pytest を促す
# .ts/.tsx/.js/.jsx → vitest + tsc 両方を促す（型エラーは再現性が高いため）
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
