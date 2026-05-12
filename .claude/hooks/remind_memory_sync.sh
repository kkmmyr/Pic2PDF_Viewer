#!/bin/bash
# PostToolUse hook — fires after git commit (Bash).
# Injects a context reminder to update memory/pending_tasks.md.
#
# Reads tool input as JSON from stdin.

input=$(cat)

cmd=$(echo "$input" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(d.get('tool_input', {}).get('command', ''))
" 2>/dev/null) || true

case "$cmd" in
    *git\ commit*) ;;
    *) exit 0 ;;
esac

cat <<'EOF'
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "git commit が完了しました。memory/pending_tasks.md の「作業中（未コミット）」欄と完了タスクを更新してください（/sync-memory で一括チェックできます）。"}}
EOF
exit 0
