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
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "git commit が完了しました。CLAUDE.md「タスク完了後の必須アクション」③に従い memory/ を更新してください（project/feedback/reference のいずれか該当するもの。ズレの棚卸しは /sync-memory）。"}}
EOF
exit 0
