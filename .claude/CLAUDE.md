# プロジェクト設定

同人誌・漫画・小説を対象としたマルチソース閲覧 Web アプリ。WebP 画像・ZIP の PDF 化とブラウザ閲覧に加え、小説向けに OCR（yomitoku）+ Embedding（bge-m3）+ Qwen による RAG 全文検索・マルチターン QA・キャラクター辞典・書籍サマリ生成を備える。Kindle キャプチャ連携あり。サイドバーは同人誌 / 漫画 / 小説の 3 カテゴリ構成（source: doujin / comic / novel）。

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

ソースは `docs/*.md` のまま、ビルド時に `frontend/public/site/` へ HTML を生成する（Vite の publicDir 配下）。これにより:

- **Vite dev** (`:5176`): `http://localhost:5176/site/index.html` で閲覧可
- **リリース統合** (`:8090`): `http://localhost:8090/site/index.html`（Vite dist 経由）と `http://localhost:8090/docs-html/`（FastAPI マウント、後方互換）の両方で閲覧可
- **mkdocs serve** (`:8000`): 開発時プレビュー

Claude が読み書きするのは **Markdown 側**、ユーザーが閲覧用に見るのが **HTML 側**、という役割分担。

```powershell
# 初回セットアップ（一度だけ）
uv tool install mkdocs --with mkdocs-material --with mkdocs-mermaid2-plugin

# uv tool 配置先（~/.local/bin）を PATH に追加（一度だけ、PowerShell 再起動が必要）
uv tool update-shell

# ビルド（frontend/public/site/ に出力、.gitignore 配下）
# Vite dev 起動中に site_dir 全 wipe で PermissionError になるため、通常は --dirty で増分ビルドする
mkdocs build --dirty

# テーマ更新時など、フルクリーンビルドしたい場合は Vite dev を停止してから:
# mkdocs build

# 開発時プレビュー（http://localhost:8000、自動リロード）
mkdocs serve
```

**注意**: `update-shell` 実行後に **PowerShell を一度閉じて開き直す** 必要があります。再起動せずに同じセッションで試したい場合は `$env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"` で一時的にパスを通せます。

Mermaid 図は ` ```mermaid` フェンスでそのまま記述する（mkdocs-material が描画）。

**注意**: Markdown 編集後は `mkdocs build --dirty` で HTML 反映が必要（CI / 手動）。`frontend/public/site/` 配下は git 管理外なので、サーバ起動前に最低 1 回ビルドしておくこと。`npm run build` 時は `frontend/dist/site/` にもコピーされる（dist サイズが site 分肥大化）。

## スラッシュコマンド

`/big-files` `/audit` `/check-docs` `/refactor-status` `/changelog` `/sync-memory` `/grill-me` を提供。詳細は [README.md](README.md) を参照。
