# `.claude/` ディレクトリ

Claude Code（このプロジェクトでアシスタントとして動く CLI）の設定一式。

セッション開始時に **自動ロードされるもの**（`CLAUDE.md`）と、**description ベースで必要時にだけ自動発動するもの**（`skills/`）、**手動で `/` 呼び出しするもの**（`commands/`）、**ツール実行に連動するもの**（`hooks/`）に分けて配置している。

---

## ファイル一覧

| パス | 役割 | 自動ロード | 更新タイミング |
|---|---|:---:|---|
| [CLAUDE.md](CLAUDE.md) | プロジェクトの最上位指示。MCP / 設計書リンク / 起動方法 | ✅ | 設計書追加・MCP 追加・起動方法変更時 |
| [skills/](skills/) | description ベースで自動発動する規約・ノウハウ集 | △ (description のみ) | 新しい共通パターンが確立したら追加 |
| [commands/](commands/) | スラッシュコマンド定義（`/<filename>` で呼べる） | ❌ | 頻用作業を発見したら新規作成 |
| [hooks/check_docs_updated.sh](hooks/check_docs_updated.sh) | PreToolUse: 実装変更前に docs/ が更新されているか確認 | ❌ (実行のみ) | 判定ロジック改善時 |
| [hooks/remind_tests.sh](hooks/remind_tests.sh) | PostToolUse: 大きめの実装変更時にテスト実行を促す | ❌ (実行のみ) | 対象ファイル拡張時 |
| [hooks/remind_deps_install.sh](hooks/remind_deps_install.sh) | PostToolUse: `pyproject.toml` / `package.json` 等の編集時に `uv sync` / `npm install` を促す | ❌ (実行のみ) | 言語追加時 |
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

---

## スキル一覧（現状）

| スキル | 自動発動するタイミング |
|---|---|
| `git-workflow` | git の commit / PR / branch / mv / rm 操作時 |
| `test-writing` | pytest / vitest のテストコード追加・修正時 |
| `frontend-conventions` | `frontend/src/` 配下の React/TypeScript コード編集時 |
| `backend-conventions` | `backend/` 配下の Python/FastAPI コード編集時 |

定義は [skills/](skills/) を参照。詳細は各 SKILL.md および `references/` 配下に記載。

---

## スラッシュコマンド一覧（現状）

| コマンド | 用途 |
|---|---|
| `/test` | backend pytest + frontend vitest を順次実行 |
| `/typecheck` | TypeScript 型チェック (`tsc --noEmit`) |
| `/refactor-status` | リファクタ計画書の未着手 Phase をサマリ |
| `/big-files` | 肥大化候補ファイル上位 10 件を表示 |
| `/check-docs` | 設計書と実装の整合性をクロスチェック |
| `/audit` | npm audit + uv audit でセキュリティ脆弱性を確認 |
| `/changelog` | 直近コミットから 変更履歴.md 追記の草稿を生成 |

定義は [commands/](commands/) を参照。

---

## アーキテクチャ詳細はどこ？

ファイル構成・役割マップは **このディレクトリではなく** [`docs/02_基本設計/アーキテクチャ詳細.md`](../docs/02_基本設計/アーキテクチャ詳細.md) にある。コード変更タスク時は最初にこのファイルを読み込むこと（`CLAUDE.md` で指示済み）。

`skills/` 配下に置かない理由: skills の description は常時ロードされるため、肥大化しやすい「ファイルマップ」を含めるとオーバーヘッドが増える。
