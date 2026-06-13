#!/bin/bash
# Self-tests for .claude/hooks/*.sh
# 実行: bash .claude/hooks/tests/run_hook_tests.sh
# 全 PASS で exit 0、1件でも FAIL で exit 1
set -u
ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
if [ -z "$ROOT" ]; then ROOT=$(cd "$(dirname "$0")/../../.." && pwd); fi
HOOKS="${ROOT}/.claude/hooks"

# python3 → python フォールバック
if command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
else echo "FATAL: python3/python が見つかりません" >&2; exit 1; fi

# 色付き出力
RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[0;33m'; RESET=$'\033[0m'
PASS_COUNT=0; FAIL_COUNT=0; FAILED_NAMES=()

pass() { PASS_COUNT=$((PASS_COUNT+1)); echo "${GREEN}PASS${RESET} $1"; }
fail() { FAIL_COUNT=$((FAIL_COUNT+1)); FAILED_NAMES+=("$1"); echo "${RED}FAIL${RESET} $1"; [ -n "${2:-}" ] && echo "       $2"; }

# hook への payload 生成
payload_for() { printf '{"tool_input":{"file_path":"%s"}}' "$1"; }

# Edit ペイロード生成ヘルパー（python で json.dumps）
build_edit_payload() {
  local file_path="$1"
  local new_string="$2"
  $PY -c "
import json, sys
print(json.dumps({
  'tool_input': {
    'file_path': sys.argv[1],
    'new_string': sys.argv[2]
  }
}))
" "$file_path" "$new_string"
}

# fixture cleanup
FIXTURES=(); SANDBOX=""
cleanup() {
  for f in "${FIXTURES[@]}"; do rm -f "$f" 2>/dev/null; done
  [ -n "$SANDBOX" ] && [ -d "$SANDBOX" ] && rm -rf "$SANDBOX"
}
trap cleanup EXIT

echo "${YELLOW}== .claude/hooks セルフテスト ==${RESET}"
echo "repo: ${ROOT}"
echo "python: ${PY}"
echo

# ─────────────────────────────────────────
# Case 1: linter バイナリ存在チェック
# ─────────────────────────────────────────
echo "--- Case 1: linter バイナリ存在チェック ---"

ruff_ok=true
prettier_ok=true
eslint_ok=true

if ! (cd "$ROOT/backend" && uv run ruff --version >/dev/null 2>&1); then
  ruff_ok=false
fi
if [ ! -f "$ROOT/frontend/node_modules/.bin/prettier" ] && [ ! -f "$ROOT/frontend/node_modules/.bin/prettier.cmd" ]; then
  prettier_ok=false
fi
if [ ! -f "$ROOT/frontend/node_modules/.bin/eslint" ] && [ ! -f "$ROOT/frontend/node_modules/.bin/eslint.cmd" ]; then
  eslint_ok=false
fi

if $ruff_ok && $prettier_ok && $eslint_ok; then
  pass "Case 1: linter バイナリ全て存在"
else
  hints=""
  $ruff_ok || hints="${hints} ruff 未発見(cd backend && uv sync);"
  $prettier_ok || hints="${hints} prettier 未発見(cd frontend && npm install);"
  $eslint_ok || hints="${hints} eslint 未発見(cd frontend && npm install);"
  fail "Case 1: linter バイナリ欠落" "$hints"
fi

# ─────────────────────────────────────────
# Case 2: lint_check.sh が backend .py の違反を検出する
# ─────────────────────────────────────────
echo "--- Case 2: lint_check.sh が backend .py の ruff 違反を検出 ---"

py_fixture="${ROOT}/backend/__hooktest_lint__.py"
printf 'import os\nx = 1\n' > "$py_fixture"
FIXTURES+=("$py_fixture")

output2=$(payload_for "$py_fixture" | bash "$HOOKS/lint_check.sh" 2>&1)
if echo "$output2" | grep -qi "Ruff"; then
  pass "Case 2: lint_check.sh が ruff 違反を検出"
else
  fail "Case 2: lint_check.sh が ruff 違反を検出できていない" "出力: $(echo "$output2" | head -3)"
fi

# ─────────────────────────────────────────
# Case 3: lint_check.sh が frontend .ts の違反を検出する
# ─────────────────────────────────────────
echo "--- Case 3: lint_check.sh が frontend .ts の prettier 違反を検出 ---"

ts_fixture="${ROOT}/frontend/src/__hooktest_lint__.ts"
printf 'const  a=1;export  const b=2\n' > "$ts_fixture"
FIXTURES+=("$ts_fixture")

output3=$(payload_for "$ts_fixture" | bash "$HOOKS/lint_check.sh" 2>&1)
if echo "$output3" | grep -qi "Prettier"; then
  pass "Case 3: lint_check.sh が Prettier 違反を検出"
else
  fail "Case 3: lint_check.sh が Prettier 違反を検出できていない" "出力: $(echo "$output3" | head -3)"
fi

# ─────────────────────────────────────────
# Case 4: lint_check.sh が免除パスで無反応（exit 0・出力なし）
# ─────────────────────────────────────────
echo "--- Case 4: lint_check.sh が免除パスで無反応 ---"

case4_ok=true
for exempt_path in "${ROOT}/docs/hooktest.md" "${ROOT}/.claude/hooktest.sh"; do
  out=$(payload_for "$exempt_path" | bash "$HOOKS/lint_check.sh" 2>&1)
  byte_count=$(echo -n "$out" | wc -c)
  if [ "$byte_count" -gt 0 ]; then
    fail "Case 4: 免除パス ${exempt_path##*/} で出力あり" "出力: $(echo "$out" | head -2)"
    case4_ok=false
  fi
done
$case4_ok && pass "Case 4: 免除パスで出力なし（silent-skip 正常）"

# ─────────────────────────────────────────
# Case 5a: remind_tests.sh が backend .py で valid JSON + "/test" または "pytest" を返す
# ─────────────────────────────────────────
echo "--- Case 5a: remind_tests.sh が backend .py で valid JSON + pytest を返す ---"

py_new_string=$(printf 'def f0():\n    return 0\n%.0s' {1..12})
payload5a=$(build_edit_payload "${ROOT}/backend/some_service.py" "$py_new_string")
output5a=$(echo "$payload5a" | bash "$HOOKS/remind_tests.sh" 2>&1)

if echo "$output5a" | $PY -c "import json,sys; d=json.load(sys.stdin); sys.exit(0)" 2>/dev/null; then
  if echo "$output5a" | grep -qi "pytest\|/test"; then
    pass "Case 5a: remind_tests.sh が valid JSON + pytest キーワードを返す"
  else
    fail "Case 5a: valid JSON だが pytest/test キーワードが含まれない" "出力: $(echo "$output5a" | head -3)"
  fi
else
  fail "Case 5a: 出力が valid JSON でない" "出力: $(echo "$output5a" | head -3)"
fi

# ─────────────────────────────────────────
# Case 5b: remind_tests.sh が frontend .tsx で valid JSON を返す
# ─────────────────────────────────────────
echo "--- Case 5b: remind_tests.sh が frontend .tsx で valid JSON を返す ---"

tsx_new_string=$(printf 'export function C0() { return null }\n%.0s' {1..12})
payload5b=$(build_edit_payload "${ROOT}/frontend/src/components/SomeComponent.tsx" "$tsx_new_string")
output5b=$(echo "$payload5b" | bash "$HOOKS/remind_tests.sh" 2>&1)

if echo "$output5b" | $PY -c "import json,sys; json.load(sys.stdin); sys.exit(0)" 2>/dev/null; then
  pass "Case 5b: remind_tests.sh が frontend .tsx で valid JSON を返す"
else
  # 出力が空（対象外スキップ）の場合は pass とする
  if [ -z "$(echo "$output5b" | tr -d '[:space:]')" ]; then
    pass "Case 5b: remind_tests.sh が frontend .tsx でスキップ（出力なし＝正常）"
  else
    fail "Case 5b: 出力が valid JSON でない" "出力: $(echo "$output5b" | head -3)"
  fi
fi

# ─────────────────────────────────────────
# Case 5c: remind_deps_install.sh が pyproject.toml で valid JSON + "uv sync" を返す
# ─────────────────────────────────────────
echo "--- Case 5c: remind_deps_install.sh が pyproject.toml で valid JSON + uv sync を返す ---"

output5c=$(payload_for "${ROOT}/backend/pyproject.toml" | bash "$HOOKS/remind_deps_install.sh" 2>&1)

if echo "$output5c" | $PY -c "import json,sys; json.load(sys.stdin); sys.exit(0)" 2>/dev/null; then
  if echo "$output5c" | grep -qi "uv sync"; then
    pass "Case 5c: remind_deps_install.sh が valid JSON + uv sync を返す"
  else
    fail "Case 5c: valid JSON だが uv sync が含まれない" "出力: $(echo "$output5c" | head -3)"
  fi
else
  fail "Case 5c: 出力が valid JSON でない" "出力: $(echo "$output5c" | head -3)"
fi

# ─────────────────────────────────────────
# Case 6: remind_docs_update.sh がサンドボックスでソース編集に advisory を返す（exit 2 を出さない）
# ─────────────────────────────────────────
echo "--- Case 6: remind_docs_update.sh が advisory のみ（exit 2 なし） ---"

SANDBOX=$(mktemp -d)
# サンドボックス git repo 初期化
(cd "$SANDBOX" && git init -q && git config user.email "test@test.com" && git config user.name "Test" && mkdir -p docs backend && touch docs/.gitkeep && git add -A && git commit -q -m "init") 2>/dev/null

# marker ファイル削除（冪等性確保）
HEAD6=$(cd "$SANDBOX" && git rev-parse HEAD 2>/dev/null || echo "test")
rm -f "/tmp/remind_docs_${HEAD6}.marker" 2>/dev/null

payload6=$(payload_for "${SANDBOX}/backend/foo.py")
output6=$(echo "$payload6" | bash "$HOOKS/remind_docs_update.sh" 2>&1)
exit6=$?

if [ "$exit6" -eq 2 ]; then
  fail "Case 6: remind_docs_update.sh が exit 2 を返した（ブロックしてはいけない）" "exit code: $exit6"
else
  if echo "$output6" | grep -qi "additionalContext"; then
    pass "Case 6: remind_docs_update.sh が advisory（exit 0）で additionalContext を返す"
  else
    # advisory が出なかった（対象外と判断された）場合も exit 2 でなければ OK
    if [ "$exit6" -eq 0 ]; then
      pass "Case 6: remind_docs_update.sh が exit 0（ブロックなし）"
    else
      fail "Case 6: 予期しない exit code" "exit: $exit6, 出力: $(echo "$output6" | head -2)"
    fi
  fi
fi

# ─────────────────────────────────────────
# Case 7: bash -n 構文OK（6 hook 全部）
# ─────────────────────────────────────────
echo "--- Case 7: 6 hook の bash -n 構文チェック ---"

hook_files=(
  "$HOOKS/lint_check.sh"
  "$HOOKS/mkdocs_build.sh"
  "$HOOKS/remind_deps_install.sh"
  "$HOOKS/remind_docs_update.sh"
  "$HOOKS/remind_memory_sync.sh"
  "$HOOKS/remind_tests.sh"
)

case7_ok=true
for hf in "${hook_files[@]}"; do
  if bash -n "$hf" 2>/dev/null; then
    :
  else
    fail "Case 7: bash -n 失敗: ${hf##*/}"
    case7_ok=false
  fi
done
$case7_ok && pass "Case 7: 6 hook 全て bash -n OK"

# ─────────────────────────────────────────
# サマリ
# ─────────────────────────────────────────
echo
echo "─────────────────────────────────────────"
if [ "$FAIL_COUNT" -eq 0 ]; then
  echo "${GREEN}ALL PASS${RESET}: ${PASS_COUNT} 件すべて成功"
  exit 0
else
  echo "${RED}FAILED${RESET}: ${FAIL_COUNT} 件失敗 / ${PASS_COUNT} 件成功"
  for n in "${FAILED_NAMES[@]}"; do echo "  - $n"; done
  exit 1
fi
