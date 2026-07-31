# プロジェクト設定

同人誌・漫画・小説を対象としたマルチソース閲覧 Web アプリ。WebP 画像・ZIP の PDF 化とブラウザ閲覧に加え、小説向けに OCR（yomitoku）+ Embedding（bge-m3）+ Qwen による RAG 全文検索・マルチターン QA・キャラクター辞典・書籍サマリ生成を備える。Kindle キャプチャ連携あり。
**source の 3 値: `doujin` / `comic` / `novel`**（サイドバーの 3 カテゴリに対応）

## 環境の癖（推測しにくい部分）

- Python は **uv** で管理。`pip install` ではなく `uv add` / `uv sync`、実行は `uv run`。マニフェスト: ルート `pyproject.toml`（workspace 定義） + `backend/pyproject.toml`（backend 依存）
- **uv workspace モノレポ**: `backend` / `kindle-pdf` / `common/llm` の 3 メンバー。**初回セットアップはルートで `uv sync` を 1 回**（`.venv` はルートに作成される）
- Node は npm。`frontend/package.json`
- 開発ポートは `:8766` (backend) / `:5176` (frontend)。リリース統合は `:8090`
- OCR ツール群（`kindle-pdf/`）は別 uv workspace member。GPU 依存は `[dependency-groups.gpu]` で分離
- `.bat` / `.sh` スクリプトは **`scripts/` 配下に集約済**（ルート直下には存在しない）
- **pre-commit hooks**（`.pre-commit-config.yaml`）が設定済み — commit 時に ruff --fix（Python）/ prettier（TS/TSX/CSS）が自動整形される
- **`docs/` は 3 バケット構成**: `design/`（静的設計書・編集イン・プレース）/ `log/`（生きた文書・変更履歴等）/ `archive/`（凍結）。`docs/**/*.md` か `mkdocs.yml` を含むコミットは `check-docs` pre-commit hook（`scripts/maintenance/check_docs.py`）でリンク切れ・nav 孤児・`log/変更履歴.md` の行数超過（800行）を機械チェックされ、違反時はコミットがブロックされる

## 起動コマンド

```bash
cd backend && uv run uvicorn main:app --reload --port 8766   # :8766
cd frontend && npm run dev                                   # :5176
```

## 頻用コマンド

```bash
# テスト
cd backend && uv run pytest -q
cd frontend && npm run test

# テスト + カバレッジ計測（HTML レポート: backend/htmlcov/ または frontend/coverage/）
cd backend && uv run pytest --cov
cd frontend && npm run test:coverage

# リント・フォーマット
cd backend && uv run ruff check . && uv run ruff format .
cd frontend && npm run lint && npm run format

# 型チェック（tsc --noEmit は solution tsconfig のため 0 ファイル検査の no-op — 使わない）
cd frontend && npx tsc -b

# OpenAPI から TypeScript 型を再生成（backend :8766 起動中に実行）
cd frontend && npm run generate:types
```

## フロントエンド変更の完了条件

`frontend/src/` のうち、UI・画面遷移・操作・レイアウト・レスポンシブ・アクセシビリティに影響する変更は、自動テスト等に加えて、変更内容に応じて実ブラウザで以下を確認する。

- デスクトップ幅とモバイル幅で、対象画面の表示・主要導線が成立する
- Tab / Shift+Tab / Enter / Escape など、対象機能に関係する主要操作をキーボードで実行できる
- ブラウザのコンソールに、変更による新規エラーや未処理例外がない
- 修正後に同じ操作を再実行し、問題が解消している

型・データ変換・テスト・コメントのみなど画面へ影響しない変更では、実ブラウザ確認を省略してよい。環境や依存サービスの都合で必要な確認を実施できない場合は、未確認項目・理由・残存リスクを完了報告に明記する。

## 設計書

`docs/` 配下に要件定義・基本設計（アーキテクチャ詳細含む）・詳細設計・API 仕様・OCR・セキュリティ・変更履歴がある。設計判断の理由は `docs/design/基本設計/ADR/` に ADR として記録。
mkdocs セットアップ・HTML 配信の詳細は `docs/design/環境構築/` を参照。

## タスク完了後の必須アクション

**設計の意図・挙動・API・データ構造に影響するコード変更を完了したら、ユーザーに求められなくても必ず以下を実施すること：**

1. **関連する設計書（`docs/` 配下）を更新する** — どのファイルが対象かは変更内容から判断する
2. **`docs/log/変更履歴.md` に追記する** — `## YYYY-MM-DD: type — タイトル` 形式で直近エントリの上に挿入。本ファイルが 800 行を超えたら前週分を `docs/log/変更履歴/YYYY-Www.md` へ切り出す（アーカイブ索引テーブルに追記）
3. **永続化が必要な知識の正本を更新する** — 継続必須の開発ルールは `AGENTS.md`、設計・進捗の事実は `docs/` に反映する。`~/.codex/memories/` は生成状態なので手動編集しない

**不要なケース（スキップしてよい）**: typo 修正・コメント整理・テスト追加・フォーマットのみの変更。迷ったら実施する側に倒す。

本節が正本。編集直前 (①) は `.codex/hooks/remind_docs_update.sh`、commit 後 (③) は `.codex/hooks/remind_memory_sync.sh` が advisory で短く再通知する。①の設計書振り分けの詳細は `docs-workflow` skill を参照。

## 計画候補の振り分け

新しい改善候補を起票する前に1問だけ判定する: **「ユーザーから見た振る舞いが新しく増える/変わるか？」**

| 判定 | 行き先 |
|---|---|
| Yes（新機能・新体験） | `docs/log/計画/バックログ.md`（A/B/C 階層） |
| No・外部挙動を変えない内部構造改善 | `docs/log/計画/リファクタリング計画書.md` **§ 未着手候補 — リファクタリング** |
| No だが依存/インフラ/性能が変わる | `docs/log/計画/リファクタリング計画書.md` **§ 未着手候補 — 技術メンテナンス** |

**新機能をリファクタリング計画書に Phase として起票しない**。

## サブエージェント運用

独立して進められる大規模タスクは、利用可能な場合にサブエージェントへ切り出してよい。委任前に、各担当について次を明示する。

- **読み取り専用調査か、書き込みを伴う作業か**
- **担当範囲**（機能・ディレクトリ・ファイル・確認観点）
- **書き込み所有者**（同じファイルを複数エージェントが同時編集しない）
- **統合責任者**（原則としてメインセッションが設計判断・統合・最終検証を担う）

調査・ログ分析・テスト原因分析・独立レビューなどは、読み取り専用の委任を優先する。書き込みを並列化するのは所有範囲が重ならず、最後に安全に統合できる場合に限る。分割による手戻りが大きい箇所はメインセッションで実装する。

### モデル別の委任基準

- **`luna-triage`（Luna）**: 機械検証可能な監査、ログ分類、関連ファイル抽出、構造化草稿に使う。読み取り専用とし、修正、再試行、DB・Git・公開状態の変更を任せない。
- **`terra-focused-worker`（Terra）**: 所有ファイル、受入条件、検証方法が明確な小規模実装に使う。要件・設計判断、複数領域への波及、状態変更が必要になったらメインへ戻す。
- **`docs-cross-checker`（Terra）**: 長文設計書と実装の横断確認に使い、差分の事実だけを返す。修正は行わない。
- **`refactor-planner`（Sol）**: 大規模リファクタの影響分析、依存順序、段階計画に使う。実装は行わない。
- **メインエージェント（Sol）**: 要件、設計、統合、最終検証、commit、push、deploy、公開データ変更の採否に責任を持つ。

Luna完結は、読み取り専用、範囲限定、客観的判定器あり、誤判定で状態が変わらない、意味的な最終判断なし、失敗時fail closedの全条件を満たす場合に限る。詳細は `docs/design/環境構築/Codexサブエージェント運用.md` を正本とする。
