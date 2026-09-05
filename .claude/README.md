# `.claude/` ディレクトリ

Claude Code（このプロジェクトでアシスタントとして動く CLI）の設定一式。

セッション開始時に **自動ロードされるもの**（`CLAUDE.md`）と、**description ベースで必要時にだけ自動発動するもの**（`skills/`）、**手動で `/` 呼び出しするもの**（`commands/`）、**ツール実行に連動するもの**（`hooks/`）、**メイン session が明示的にサブエージェントとして切り出すもの**（`agents/`）に分けて配置している。

---

## ファイル一覧

| パス | 役割 | 自動ロード | 更新タイミング |
|---|---|:---:|---|
| [CLAUDE.md](CLAUDE.md) | プロジェクト概要 + 環境の癖（uv 必須）+ 起動コマンド | ✅ | 起動方法・環境変更時 |
| [skills/](skills/) | description ベースで自動発動する規約・ノウハウ集 | △ (description のみ) | 新しい共通パターンが確立したら追加 |
| [commands/](commands/) | スラッシュコマンド定義（`/<filename>` で呼べる） | ❌ | 頻用作業を発見したら新規作成 |
| [hooks/](hooks/) | ツール実行の前後に走る advisory reminder script 群（個別一覧は [hooks/README.md](hooks/README.md) が正） | ❌ (実行のみ) | 新しい hook を追加・変更したら |
| [agents/](agents/) | メイン session が Agent ツールで明示的に呼ぶサブエージェント定義（長文コンテキストをメイン session から隔離する用途） | ❌ | 新しい定型監査・分析タスクを切り出したら |
| [settings.json](settings.json) | hooks 登録 + 共有 permissions | ❌ | hooks 追加・共有 permission 追加時 |
| `settings.local.json` | 個人別 permissions（`.gitignore` 対象） | ❌ | 個別 PC で許可を増やす時 |

> **「自動ロード」**: Claude Code がセッション開始時に文脈に取り込むかどうか。
> - `CLAUDE.md` のみ全文ロード
> - `skills/` は **description だけが常時ロード** され、本体（SKILL.md）は description にマッチした作業を始めたタイミングで自動展開される。`references/` 配下は SKILL.md から明示参照されたときだけ読まれる

---

## 設計原則

### `skills/` に置くもの

- **特定の作業（git 操作・テスト追加・フロント/バック編集等）に紐づく規約・ノウハウ**
- 1 スキル = 1 ディレクトリ（`<name>/SKILL.md`）。frontmatter で `description` を 250 字以内で「何を / いつ」明示
- SKILL.md 本体を薄く保ち、詳細指示は `<name>/references/*.md` に分離してトークン節約
- description ベースで自動発動するため、CLAUDE.md からの明示リンクは不要

### `commands/` に置くもの

- 手動で起動する「定型作業」をスラッシュコマンドとして抽出
- 1 コマンド = 1 ファイル（`<name>.md`）。frontmatter で `description` を書く
- 中身は Claude への自然言語指示（実行するコマンド・報告フォーマット等）

### `hooks/` に置くもの

- ツール実行（Edit / Write 等）の **前後** に走るシェルスクリプト
- `settings.json` の `hooks` 配列で登録
- 副作用は最小に。ブロックする場合は明確な指示メッセージを返す
- スキルと違い**強制力がある**（モデルの判断ではなく機械的に実行される）
- セルフテスト: `hooks/tests/run_hook_tests.sh` で hook の挙動を「実際に走らせて assert」できる（`/check-hooks` コマンドから実行可能）

### `agents/` に置くもの

- **長文の設計書・コードを読み込む定型監査/分析タスク**をメイン session の context から隔離するために切り出す
- 1 エージェント = 1 ファイル（`<name>.md`）。frontmatter で `description`（いつ使うか）・`tools`（許可ツール）・`model` を明示
- コードは書かない・提案に留める設計が多い（実装はメイン session か別の一般エージェントに委ねる）
- `commands/` から Agent ツール経由で呼ぶ（例: `/check-docs` → `docs-cross-checker`）か、ユーザー/メイン session が直接 Agent ツールで呼ぶ

---

## スキル一覧（現状）

| スキル | 自動発動するタイミング |
|---|---|
| `architecture-overview` | 新機能追加・複数ファイル横断の変更開始時、全体構成への質問時 |
| `docs-workflow` | 設計の意図を変えるソース編集時（設計書→変更履歴→ソースの順序を案内） |
| `git-workflow` | git の commit / PR / branch / mv / rm 操作時 |
| `test-writing` | pytest / vitest のテストコード追加・修正時 |
| `frontend-conventions` | `frontend/src/` 配下の React/TypeScript コード編集時 |
| `backend-conventions` | `backend/` 配下の Python/FastAPI コード編集時 |
| `worktree-workflow` | git worktree を使った並列作業（大型リファクタ・機能開発）を始める際 |
| `grill-me` | `/grill-me <機能名>` で明示的に呼び出した時。要件が曖昧な新機能・リファクタの要件を対話で固める |

定義は [skills/](skills/) を参照。詳細は各 SKILL.md および `references/` 配下に記載。
本表は手動転記のため実体とズレることがある —鮮度は `check_claude_drift.py`（`/cleanup` 問い4）が機械チェックする。

---

## スラッシュコマンド一覧（現状）

| コマンド | 用途 |
|---|---|
| `/refactor-status` | リファクタ計画書の未着手 Phase をサマリ |
| `/big-files` | 肥大化候補ファイル上位 10 件を表示 |
| `/check-docs` | 設計書と実装の整合性をクロスチェック |
| `/audit` | npm audit + uv audit でセキュリティ脆弱性を確認 |
| `/changelog` | 直近コミットから 変更履歴.md 追記の草稿を生成 |
| `/sync-memory` | 永続メモリと git log・計画書のズレを検出して更新 |
| `/check-hooks` | hooks セルフテストを実行して PASS/FAIL を報告 |
| `/cleanup` | 月次点検: 未使用 skill / 古い docs / 肥大化 / .claude ドリフトを可視化 |
| `/feature-status` | 機能バックログ（A/B/C 階層）の未着手・保留・完了状況をサマリ |

通常のテスト実行・型チェックは Bash で直接呼ぶ（`cd backend && uv run pytest` 等）。コマンド化していたが、project-specific な情報量が少ないため削除済み。実行コマンド一覧は `test-writing` skill を参照。

定義は [commands/](commands/) を参照。

---

## エージェント一覧（現状）

| エージェント | いつ使うか | 呼び出し元 |
|---|---|---|
| `docs-cross-checker` | 設計書 ↔ 実装の整合性チェック。長文の設計書をメイン context に乗せず分析したい時 | `/check-docs` |
| `refactor-planner` | 既存のリファクタリング計画書と現状コードを照合し、次のリファクタ対象の段階的計画を提案する時 | 大規模リファクタ着手前にメイン session が直接呼ぶ（専用コマンドなし） |

定義は [agents/](agents/) を参照。

---

## ファイルマップはどこ？

ファイル構成・役割マップは **このディレクトリではなく** バックエンド／フロントエンドの 2 ファイルに分割されている:

- [`バックエンド ファイルマップ`](../docs/design/詳細設計/詳細設計書_バックエンド_ファイルマップ.md) — backend / Kindleの自動生成一覧（共通責務は別のバックエンド設計）
- [`docs/design/詳細設計/詳細設計書_フロントエンド_ファイルマップ.md`](../docs/design/詳細設計/詳細設計書_フロントエンド_ファイルマップ.md) — フロントエンドのファイルマップ

コード変更タスク時はまず該当する側を読み込むこと（`CLAUDE.md` で指示済み）。

`skills/` 配下に置かない理由: skills の description は常時ロードされるため、肥大化しやすい「ファイルマップ」を含めるとオーバーヘッドが増える。
