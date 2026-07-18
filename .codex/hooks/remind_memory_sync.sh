#!/bin/bash
# PostToolUse hook — fires after git commit (Bash).
# Injects a context reminder to update memory/pending_tasks.md.
#
# Reads tool input as JSON from stdin.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
input=$(cat)

cmd=$(printf '%s' "$input" | python3 "$SCRIPT_DIR/hook_input.py" command 2>/dev/null) || true

case "$cmd" in
    *git\ commit*) ;;
    *) exit 0 ;;
esac

cat <<'EOF'
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "git commit が完了しました。AGENTS.md「タスク完了後の必須アクション」③に従い、永続化が必要なルールは AGENTS.md、設計・進捗の事実は docs/ に反映してください（生成状態の Codex memories は手動編集しません）。"}}
EOF
exit 0
