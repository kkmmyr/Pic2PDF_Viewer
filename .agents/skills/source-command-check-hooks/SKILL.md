---
name: "source-command-check-hooks"
description: ".codex/hooks のセルフテストを実行して結果を報告する"
---

# source-command-check-hooks

Use this skill when the user asks to run the migrated source command `check-hooks`.

## Command Template

以下を実行して、hooks セルフテストの結果を報告してください。

```bash
bash .codex/hooks/tests/run_hook_tests.sh
```

最後のサマリ行（全 PASS か、失敗件数）を報告すれば十分です。すべての出力を貼り付ける必要はありません。

何を検証しているか:

- `lint_check.sh` が backend .py / frontend .ts の lint 違反を実際に検出するか（silent-skip の恒久検出）
- linter バイナリ（ruff / prettier / eslint）が存在するか（無ければ `cd backend && uv sync` / `cd frontend && npm install` の案内付きで fail）
- `remind_tests.sh` / `remind_deps_install.sh` が valid JSON + 期待キーワードを返すか
- `remind_docs_update.sh` が advisory（exit 0）のまま動くか（ブロックしないことを確認）
- 5 hooks 全ての `bash -n` 構文 OK

失敗した場合:

- 失敗したケース名と原因の要約を報告
- hook 側の不具合か fixture 側かを切り分けてから修正提案（勝手に実装しない）

**`.codex/hooks/` を変更したら、コミット前に必ずこのコマンドを実行してください**。
