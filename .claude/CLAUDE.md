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

# 型チェック
cd frontend && npx tsc --noEmit

# OpenAPI から TypeScript 型を再生成（backend :8766 起動中に実行）
cd frontend && npm run generate:types
```

## 設計書

`docs/` 配下に要件定義・基本設計（アーキテクチャ詳細含む）・詳細設計・API 仕様・OCR・セキュリティ・変更履歴がある。設計判断の理由は `docs/02_基本設計/ADR/` に ADR として記録。
mkdocs セットアップ・HTML 配信の詳細は `docs/04_環境構築/` を参照。

## タスク完了後の必須アクション

**設計の意図・挙動・API・データ構造に影響するコード変更を完了したら、ユーザーに求められなくても必ず以下を実施すること：**

1. **関連する設計書（`docs/` 配下）を更新する** — どのファイルが対象かは変更内容から判断する
2. **`docs/05_記録/変更履歴.md` に追記する** — `## YYYY-MM-DD: type — タイトル` 形式で直近エントリの上に挿入
3. **`memory/` を更新する** — project / feedback / reference のいずれか該当するものを更新・追加

**不要なケース（スキップしてよい）**: typo 修正・コメント整理・テスト追加・フォーマットのみの変更。迷ったら実施する側に倒す。

## 計画候補の振り分け

新しい改善候補を起票する前に1問だけ判定する: **「ユーザーから見た振る舞いが新しく増える/変わるか？」**

| 判定 | 行き先 |
|---|---|
| Yes（新機能・新体験） | `docs/01_要件定義/バックログ.md`（A/B/C 階層） |
| No・外部挙動を変えない内部構造改善 | `docs/06_リファクタリング/リファクタリング計画書.md` **§ 未着手候補 — リファクタリング** |
| No だが依存/インフラ/性能が変わる | `docs/06_リファクタリング/リファクタリング計画書.md` **§ 未着手候補 — 技術メンテナンス** |

**新機能をリファクタリング計画書に Phase として起票しない**。

実装にあたってはトークンを節約するためにOpus/Sonnetを適切にサブエージェントとして切り出して実行し、このメインセッション(Fable 5)は設計と監査、レビューに専念してください。実装難易度が特に高いところはこのセッションでやってよいです
