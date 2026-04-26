#!/bin/bash
# PreToolUse hook for Edit/Write.
# Allows the edit if either:
#   - the target is exempt (docs/, .claude/, .md, configs, tests, lockfiles, etc.)
#   - docs/ has any pending git changes (interpreted as "design docs were updated this session")
# Otherwise blocks with a JSON response that asks the user to update design docs first.
#
# Reads tool input as JSON from stdin: { "tool_name": "...", "tool_input": { "file_path": "...", ... } }

set -e

input=$(cat)

# Extract file_path from JSON input (basic parsing without jq dependency)
file_path=$(echo "$input" | grep -oE '"file_path"\s*:\s*"[^"]+"' | head -1 | sed -E 's/.*"file_path"\s*:\s*"([^"]+)".*/\1/')

# If file_path is empty, allow (defensive)
if [ -z "$file_path" ]; then
    exit 0
fi

# Normalize backslashes to forward slashes for matching
normalized=$(echo "$file_path" | tr '\\' '/')

# Step 1: Always-exempt files
case "$normalized" in
    */docs/*|*/.claude/*) exit 0 ;;
    *.md|*.json|*.toml|*.lock|*.txt|*.bat|*.sh|*.yml|*.yaml|*.env|*.ini|*.cfg|*.gitignore|*.tsbuildinfo) exit 0 ;;
    */test/*|*/tests/*|*/__tests__/*|*.test.*|*.spec.*) exit 0 ;;
esac

# Step 2: Check git status of docs/
# If any docs/ files are modified/added/untracked, allow.
docs_status=$(git status --porcelain docs/ 2>/dev/null || true)
if [ -n "$docs_status" ]; then
    exit 0
fi

# Step 3: Block with JSON response
cat <<'EOF' >&2
{"continue": false, "stopReason": "設計書（docs/配下）を先に更新してから実装してください。"}
EOF
exit 2
