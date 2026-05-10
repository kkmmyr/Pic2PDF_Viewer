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

### 設計ドキュメントの HTML 配信（mkdocs-material）

ソースは `docs/*.md` のまま、ビルド時に `site/` へ HTML を生成し FastAPI が `/docs-html` で配信する（ローカル閲覧用）。Claude が読み書きするのは **Markdown 側**、ユーザーが閲覧用に見るのが **HTML 側**、という役割分担。

```powershell
# 初回セットアップ（一度だけ）
uv tool install mkdocs --with mkdocs-material --with mkdocs-mermaid2-plugin

# uv tool 配置先（~/.local/bin）を PATH に追加（一度だけ、PowerShell 再起動が必要）
uv tool update-shell

# ビルド（site/ に出力、.gitignore 配下）
mkdocs build

# 開発時プレビュー（http://localhost:8000、自動リロード）
mkdocs serve
```

**注意**: `update-shell` 実行後に **PowerShell を一度閉じて開き直す** 必要があります。再起動せずに同じセッションで試したい場合は `$env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"` で一時的にパスを通せます。

リリース統合（`:8090`）後は `http://localhost:8090/docs-html/` で閲覧可能。Mermaid 図は ` ```mermaid` フェンスでそのまま記述する（mkdocs-material が描画）。

**注意**: Markdown 編集後は `mkdocs build` で HTML 反映が必要（CI / 手動）。`site/` 配下は git 管理外なので、サーバ起動前に最低 1 回ビルドしておくこと。

## スラッシュコマンド

`/big-files` `/audit` `/check-docs` `/refactor-status` `/changelog` `/sync-memory` を提供。詳細は [README.md](README.md) を参照。
