# プロジェクト設定

同人誌・漫画・小説を対象としたマルチソース閲覧 Web アプリ。WebP 画像・ZIP の PDF 化とブラウザ閲覧に加え、小説向けに OCR（yomitoku）+ Embedding（bge-m3）+ Qwen による RAG 全文検索・マルチターン QA・キャラクター辞典・書籍サマリ生成を備える。Kindle キャプチャ連携あり。
**source の 3 値: `doujin` / `comic` / `novel`**（サイドバーの 3 カテゴリに対応）

## 環境の癖（推測しにくい部分）

- Python は **uv** で管理。`pip install` ではなく `uv add` / `uv sync`、実行は `uv run`。マニフェストは `backend/pyproject.toml` + `backend/uv.lock`
- Node は npm。`frontend/package.json`
- 開発ポートは `:8766` (backend) / `:5176` (frontend)。リリース統合は `:8090`
- OCR ツール群（`kindle-pdf/`）は別 uv プロジェクト。GPU 依存は `[dependency-groups.gpu]` で分離

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
```

## 設計書

`docs/` 配下に要件定義・基本設計（アーキテクチャ詳細含む）・詳細設計・API 仕様・OCR・セキュリティ・変更履歴がある。設計判断の理由は `docs/02_基本設計/ADR/` に ADR として記録。
mkdocs セットアップ・HTML 配信の詳細は `docs/04_環境構築/` を参照。
