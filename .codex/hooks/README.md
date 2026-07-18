# hooks/

このディレクトリには `.codex/hooks.json` から呼び出される Codex hook スクリプトが入っている。

## 一覧

| ファイル | 種別 | 役割 | ブロックする？ |
|---|---|---|---|
| `remind_docs_update.sh` | PreToolUse (Edit\|Write) | 実装変更前に `docs/` 更新を **提案**（advisory） | **しない** |
| `remind_tests.sh` | PostToolUse (Edit\|Write) | 大きめのソース変更時にテスト実行を促す | しない |
| `remind_deps_install.sh` | PostToolUse (Edit\|Write) | `pyproject.toml` / `package.json` 等の編集時に `uv sync` / `npm install` を促す | しない |
| `lint_check.sh` | PostToolUse (Edit\|Write) | backend .py → ruff check / frontend .ts/tsx/css/json → eslint + prettier --check を実行し違反を通知 | しない |
| `remind_memory_sync.sh` | PostToolUse (Bash, git commit) | git commit 後に `memory/pending_tasks.md` の更新を促す | しない |

**このプロジェクトの全 hook は advisory（追加コンテキスト挿入）のみ。exit 2 でブロックする hook は存在しない。**

advisory 型の hook は `{"hookSpecificOutput": {"hookEventName": "...", "additionalContext": "..."}}` を返す（exit 0）。

## セルフテスト

hook が「黙ってスキップ」していないことを `hooks/tests/run_hook_tests.sh` で定期確認できる。
`/check-hooks` コマンドから実行可能。

```bash
bash .codex/hooks/tests/run_hook_tests.sh
```

## 編集する際の注意

- 上記「一覧」表と `.codex/hooks.json`／実体のドリフトはセルフテストが検査する
- 全て `bash + python3` を前提にしている（Windows でも git-bash 同梱の bash で動く）
- Windows 用コマンドは Git のインストール先から `bin/bash.exe` を解決するため、リポジトリの絶対パスを埋め込まない
- `SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"` から `PROJECT_ROOT` を解決（CWD 非依存）
- プロジェクト固有のパス（`backend/` / `frontend/` / `uv run`）がハードコードされている。レイアウト変更時は併せて更新

## 一時的に無効化したい

`.codex/hooks.json` の `hooks.PreToolUse` / `hooks.PostToolUse` から該当エントリを外す。
変更後は Codex の `/hooks` で内容を確認し、更新された hook を再度 trust する。

## 新しい hook を追加する判断基準

- 人間（モデル含む）が忘れがちで、機械的に強制したいか
- advisory（追加コンテキスト挿入）で済むか（このプロジェクトでは全て advisory に統一）
- 編集 1 回ごとに走る妥当性があるか（重い処理は不向き）
- **他の仕組み（pre-commit・CI・dev server の live reload）と機能が重複していないか**

「便利そう」だけで足さない。

**撤去実績**: `mkdocs_build.sh`（docs/*.md 編集の度に `mkdocs build --dirty` を実行）は実測 ~2.2秒/回のコストがあった一方、(1) 開発時は ADR-0008 で規定済みの `mkdocs serve` が live reload を提供、(2) CI が `mkdocs build --strict` を独立実行、(3) pre-commit の `check-docs.py` が壊れたリンク/nav を commit 時に検査——と3つの既存の仕組みと完全に重複していたため撤去した。「編集の度に走る」コストに見合う固有の検証価値が残っていないかを追加判断基準にした事例。
