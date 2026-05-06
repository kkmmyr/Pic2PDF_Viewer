#!/bin/bash
# PostToolUse hook for Edit/Write — 編集ファイルに対して linter / formatter を実行する。
#
# 対象:
#   - backend/**/*.py        → uv run ruff check
#   - frontend/src/**/*.{ts,tsx,css,json}
#                            → npx eslint + npx prettier --check
#
# 違反があれば additionalContext で Claude に通知（ブロックはしない）。
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

# Normalize backslashes to forward slashes for matching
normalized=$(echo "$file_path" | tr '\\' '/')

# Skip vendor / generated / private paths
case "$normalized" in
    */node_modules/*|*/.venv/*|*/dist/*|*/coverage/*|*/.git/*) exit 0 ;;
    */data/*|*/__pycache__/*|*/.claude/*|*/docs/*) exit 0 ;;
esac

issues=""

# ── Backend (Python) ────────────────────────────────────────────────────
if [[ "$normalized" == */backend/* && "$normalized" == *.py ]]; then
    output=$(cd "$PROJECT_ROOT/backend" && uv run ruff check "$file_path" 2>&1) || true
    # Ruff: 成功時は "All checks passed!"
    if ! echo "$output" | grep -qF 'All checks passed!'; then
        issues="Ruff 違反:
$output"
    fi
fi

# ── Frontend (TS/TSX/CSS/JSON) ─────────────────────────────────────────
if [[ "$normalized" == */frontend/src/* ]]; then
    case "$normalized" in
        *.ts|*.tsx|*.css|*.json)
            eslint_out=$(cd "$PROJECT_ROOT/frontend" && npx --no-install eslint "$file_path" 2>&1) || true
            prettier_out=$(cd "$PROJECT_ROOT/frontend" && npx --no-install prettier --check "$file_path" 2>&1) || true

            # ESLint: error / warning 行があれば違反
            if echo "$eslint_out" | grep -qE 'error|warning'; then
                issues="ESLint 違反:
$eslint_out"
            fi
            # Prettier --check: 整形未完なら "Code style issues found" が出る
            if echo "$prettier_out" | grep -qF 'Code style issues'; then
                if [ -n "$issues" ]; then
                    issues="$issues

"
                fi
                issues="${issues}Prettier 整形未完:
$prettier_out"
            fi
            ;;
    esac
fi

if [ -n "$issues" ]; then
    # ensure_ascii=False で日本語を escape せずそのまま出力
    msg=$(printf '%s' "$issues" | python3 -c "import json,sys; print(json.dumps(sys.stdin.read(), ensure_ascii=False))")
    cat <<EOF
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": $msg}}
EOF
fi

exit 0
