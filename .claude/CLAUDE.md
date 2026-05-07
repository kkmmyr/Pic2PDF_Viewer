# プロジェクト設定

WebP 画像・ZIP を PDF 化してブラウザで閲覧する Web アプリ。Kindle キャプチャ連携と OCR（yomitoku）による Searchable PDF 生成機能あり。

## 環境の癖（推測しにくい部分）

- Python は **uv** で管理。`pip install` ではなく `uv add` / `uv sync`、実行は `uv run`。マニフェストは `backend/pyproject.toml` + `backend/uv.lock`
- Node は npm。`frontend/package.json`
- 開発ポートは `:8766` (backend) / `:5176` (frontend)。リリース統合は `:8090`（[セキュリティ設計書 §1](../docs/03_詳細設計/セキュリティ設計書.md)）
- OCR ツール群（`kindle-pdf/`）は別 uv プロジェクト。GPU 依存は `[dependency-groups.gpu]` で分離（[GPU環境セットアップ.md](../docs/04_環境構築/GPU環境セットアップ.md)）

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

`docs/` 配下に要件定義・基本設計（アーキテクチャ詳細含む）・詳細設計・API 仕様・OCR・セキュリティ・変更履歴がある。コード変更時は該当領域の設計書を確認すること。

設計判断の理由は [docs/02_基本設計/ADR/](../docs/02_基本設計/ADR/) に Architecture Decision Records として記録。

## スラッシュコマンド

`/big-files` `/audit` `/check-docs` `/refactor-status` `/changelog` `/sync-memory` を提供。詳細は [README.md](README.md) を参照。
