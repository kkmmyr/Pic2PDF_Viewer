#!/bin/bash
# PostToolUse hook for Edit/Write — 編集ファイルに対して linter / formatter を実行する。
#
# 対象:
#   - backend/**/*.py        → uv run ruff check
#   - frontend/src/**/*.{ts,tsx,css,json}
#                            → npx eslint + npx prettier --check
#
# 違反があれば additionalContext で Codex に通知（ブロックはしない）。
# Reads tool input as JSON from stdin.

set -e

# Hook script の location から project root を解決（CWD 非依存）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

input=$(cat)
mapfile -t file_paths < <(printf '%s' "$input" | python3 "$SCRIPT_DIR/hook_input.py" paths 2>/dev/null)

if [ "${#file_paths[@]}" -eq 0 ]; then
    exit 0
fi

issues=""

for file_path in "${file_paths[@]}"; do
    normalized=$(echo "$file_path" | tr '\\' '/')
    case "$normalized" in
        /*|[A-Za-z]:/*) absolute_path="$file_path" ;;
        *) absolute_path="$PROJECT_ROOT/$file_path" ;;
    esac
    [ -f "$absolute_path" ] || continue

    # Skip vendor / generated / private paths
    case "$normalized" in
        */node_modules/*|*/.venv/*|*/dist/*|*/coverage/*|*/.git/*) continue ;;
        */data/*|*/__pycache__/*|*/.claude/*|*/.codex/*|*/docs/*) continue ;;
    esac

    if [[ "/$normalized" == */backend/* && "$normalized" == *.py ]]; then
        output=$(cd "$PROJECT_ROOT/backend" && uv run ruff check "$absolute_path" 2>&1) || true
        if ! echo "$output" | grep -qF 'All checks passed!'; then
            issues="${issues}${issues:+

}Ruff 違反 ($normalized):
$output"
        fi
    fi

    if [[ "/$normalized" == */frontend/src/* ]]; then
        case "$normalized" in
            *.ts|*.tsx|*.css|*.json)
                eslint_out=$(cd "$PROJECT_ROOT/frontend" && npx --no-install eslint "$absolute_path" 2>&1) || true
                prettier_out=$(cd "$PROJECT_ROOT/frontend" && npx --no-install prettier --check "$absolute_path" 2>&1) || true
                if echo "$eslint_out" | grep -qE 'error|warning'; then
                    issues="${issues}${issues:+

}ESLint 違反 ($normalized):
$eslint_out"
                fi
                if echo "$prettier_out" | grep -qF 'Code style issues'; then
                    issues="${issues}${issues:+

}Prettier 整形未完 ($normalized):
$prettier_out"
                fi
                ;;
        esac
    fi
done

if [ -n "$issues" ]; then
    # ensure_ascii=False で日本語を escape せずそのまま出力
    msg=$(printf '%s' "$issues" | python3 -c "import json,sys; print(json.dumps(sys.stdin.read(), ensure_ascii=False))")
    cat <<EOF
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": $msg}}
EOF
fi

exit 0
