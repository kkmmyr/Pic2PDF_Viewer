#!/bin/bash
# PreToolUse hook for Edit/Write — passive reminder.
# 設計書（docs/）の事前更新を促すが、ブロックはしない（advisory）。
# 軽微な編集（typo・コメント追加・テスト調整等）まで止めると不便なため、
# 強制ではなくモデルへのヒントとして additionalContext で追加する。
#
# Reads tool input as JSON from stdin.

set -e

input=$(cat)
file_path=$(echo "$input" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('file_path',''))" 2>/dev/null || true)

if [ -z "$file_path" ]; then
    exit 0
fi

normalized=$(echo "$file_path" | tr '\\' '/')

# Step 1: 対象外ファイル
case "$normalized" in
    */docs/*|*/.claude/*) exit 0 ;;
    *.md|*.json|*.toml|*.lock|*.txt|*.bat|*.sh|*.yml|*.yaml|*.env|*.ini|*.cfg|*.gitignore|*.tsbuildinfo) exit 0 ;;
    */test/*|*/tests/*|*/__tests__/*|*.test.*|*.spec.*) exit 0 ;;
esac

# Step 2: docs/ に既に未コミットの差分があれば「設計書は更新済み」と解釈してスキップ
docs_status=$(git status --porcelain docs/ 2>/dev/null || true)
if [ -n "$docs_status" ]; then
    exit 0
fi

# Step 2.5: 同一 HEAD で既に一度通知済みならスキップ（繰り返し発火防止）
# コミット後に HEAD が変わると自動リセットされる。
head_hash=$(git rev-parse HEAD 2>/dev/null || echo "no-repo")
marker_file="/tmp/remind_docs_${head_hash}.marker"
if [ -f "$marker_file" ]; then
    exit 0
fi
touch "$marker_file"

# Step 3: ソース変更で docs/ 未更新 → advisory として additionalContext を追加
cat <<'EOF'
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "実装変更前に docs/ 配下の関連設計書を更新するのが推奨です（typo修正・小規模リファクタ等の軽微な変更は無視して構いません）。設計の意図を変える変更の場合は、設計書と docs/05_記録/変更履歴.md の更新をこの編集に先行させてください。"}}
EOF
exit 0
