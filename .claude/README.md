# `.claude/` ディレクトリ

Claude Code（このプロジェクトでアシスタントとして動く CLI）の設定一式。

セッション開始時に **自動ロードされるもの**（`CLAUDE.md` / `rules/`）と、**必要時にだけ参照するもの**（コマンド・hooks）を分けて配置している。

---

## ファイル一覧

| パス | 役割 | 自動ロード | 更新タイミング |
|---|---|:---:|---|
| [CLAUDE.md](CLAUDE.md) | プロジェクトの最上位指示。MCP / 設計書リンク / 起動方法 | ✅ | 設計書追加・MCP 追加・起動方法変更時 |
| [rules/coding_conventions.md](rules/coding_conventions.md) | コーディング規約（Python / TypeScript / 共通の振る舞い縛り） | ✅ | リファクタリングで新しい共通パターンが確立したら追記 |
| [rules/git_workflow.md](rules/git_workflow.md) | git 運用ルール（コミット粒度・メッセージ書式・危険操作禁止） | ✅ | 運用方針を変えたとき |
| [rules/test_strategy.md](rules/test_strategy.md) | テスト方針（必須対象・パターン・やらないこと） | ✅ | 新しいテストパターンが確立したら追記 |
| [commands/](commands/) | スラッシュコマンド定義（`/<filename>` で呼べる） | ❌ | 頻用作業を発見したら新規作成 |
| [hooks/check_docs_updated.sh](hooks/check_docs_updated.sh) | PreToolUse: 実装変更前に docs/ が更新されているか確認 | ❌ (実行のみ) | 判定ロジック改善時 |
| [hooks/remind_tests.sh](hooks/remind_tests.sh) | PostToolUse: 大きめの実装変更時にテスト実行を促す | ❌ (実行のみ) | 対象ファイル拡張時 |
| [settings.json](settings.json) | hooks 登録 + 共有 permissions | ❌ | hooks 追加・共有 permission 追加時 |
| `settings.local.json` | 個人別 permissions（`.gitignore` 対象） | ❌ | 個別 PC で許可を増やす時 |

> **「自動ロード」**: Claude Code がセッション開始時に文脈に取り込むかどうか。✅ の付いたファイルはターン毎にトークンを消費するので、肥大化に注意。

---

## 設計原則

### `rules/` に置くもの

- **毎ターン適用すべき規範** だけを置く（規約・禁止事項・必須手順）
- **ファイルマップ・参考情報** は置かない（→ `docs/02_基本設計/アーキテクチャ詳細.md` 参照）

### `commands/` に置くもの

- 頻繁に行う「定型作業」をスラッシュコマンドとして抽出
- 1 コマンド = 1 ファイル（`<name>.md`）。frontmatter で `description` を書く
- 中身は Claude への自然言語指示（実行するコマンド・報告フォーマット等）

### `hooks/` に置くもの

- ツール実行（Edit / Write 等）の **前後** に走るシェルスクリプト
- `settings.json` の `hooks` 配列で登録
- 副作用は最小に。ブロックする場合は明確な指示メッセージを返す

---

## スラッシュコマンド一覧（現状）

| コマンド | 用途 |
|---|---|
| `/test` | backend pytest + frontend vitest を順次実行 |
| `/typecheck` | TypeScript 型チェック (`tsc --noEmit`) |
| `/refactor-status` | リファクタ計画書の未着手 Phase をサマリ |
| `/big-files` | 肥大化候補ファイル上位 10 件を表示 |
| `/check-docs` | 設計書と実装の整合性をクロスチェック |

定義は [commands/](commands/) を参照。

---

## アーキテクチャ詳細はどこ？

ファイル構成・役割マップは **このディレクトリではなく** [`docs/02_基本設計/アーキテクチャ詳細.md`](../docs/02_基本設計/アーキテクチャ詳細.md) にある。コード変更タスク時は最初にこのファイルを読み込むこと（`CLAUDE.md` で指示済み）。

`.claude/rules/` 配下に置かない理由: 毎ターン自動ロードされる場所に肥大化しやすい「ファイルマップ」を置くと、トークンオーバーヘッドが増え続けるため。
