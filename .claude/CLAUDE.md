# プロジェクト設定

WebP 画像・ZIP を PDF 化してブラウザで閲覧する Web アプリ。Kindle キャプチャ連携と OCR（yomitoku）による Searchable PDF 生成機能あり。

## 環境の癖（推測しにくい部分）

- Python は **uv** で管理。`pip install` ではなく `uv add` / `uv sync`、実行は `uv run`。マニフェストは `backend/pyproject.toml` + `backend/uv.lock`
- Node は npm。`frontend/package.json`

## 起動コマンド

```bash
cd backend && uv run uvicorn main:app --reload  # :8000
cd frontend && npm run dev                       # :5173
```

## 設計書

`docs/` 配下に要件定義・基本設計（アーキテクチャ詳細含む）・詳細設計・API 仕様・OCR・セキュリティ・変更履歴がある。コード変更時は該当領域の設計書を確認すること。
