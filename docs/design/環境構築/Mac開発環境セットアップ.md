# Mac 開発環境セットアップ

Windows をメイン環境として運用しつつ、Mac からコード編集・テスト実行・git 操作を行うための手順。

> **前提**: アプリの本番運用（NSSM サービス・Linux デプロイ）は Windows / Linux で行う。Mac は開発専用。

---

## 前提条件

| ツール | インストール方法 | 確認コマンド |
|---|---|---|
| Homebrew | `https://brew.sh` | `brew --version` |
| uv (Python 管理) | `brew install uv` | `uv --version` |
| Node.js 20+ | `brew install node` または nvm | `node --version` |
| git | 標準搭載 or `brew install git` | `git --version` |

---

## セットアップ手順

### 1. リポジトリクローン

```bash
git clone <remote-url> ~/Pic2PDF_Viewer
cd ~/Pic2PDF_Viewer
```

### 2. .env 設定

`.env.example` をコピーして `.env` を作成する。

```bash
cp .env.example .env
```

Mac 固有の設定（必要に応じて `.env` を編集）:

```dotenv
# CORS 設定（デフォルトのままでよい）
ALLOWED_ORIGINS=http://localhost:5176,http://127.0.0.1:5176

# API ベース URL（デフォルトのままでよい）
VITE_API_URL=http://localhost:8766

# OCR 機能を Mac で使う場合のみ設定（省略すると OCR 関連テストはスキップ）
# OCR_PYTHON=/Users/<user>/.venv/ocr/bin/python

# データディレクトリ（省略時: <repo>/backend/data/）
# PIC2PDF_DATA_DIR=/Users/<user>/Documents/Pic2PDF

# Linux 同期は Mac では不要（デフォルト: 無効）
# LINUX_SYNC_ENABLED=false  ← コメントのままでよい
```

### 3. バックエンドセットアップ

```bash
cd backend
uv sync --group dev
```

`.venv/` が生成されます。`activate` は不要です（`uv run` が自動検出）。

### 4. フロントエンドセットアップ

```bash
cd frontend
npm install
```

---

## 動作確認

### テスト実行

```bash
# バックエンド
cd backend && uv run pytest -q

# フロントエンド
cd frontend && npm run test
```

### アプリ起動（任意）

Mac でブラウザ確認もしたい場合:

```bash
# ターミナル 1: バックエンド
cd backend && uv run uvicorn main:app --reload --port 8766

# ターミナル 2: フロントエンド
cd frontend && npm run dev

# ブラウザで確認
open http://localhost:5176
```

---

## 注意事項

### 行末文字（CRLF/LF）

`.gitattributes` で全テキストファイルを LF に統一済み。Mac で編集・コミットしても Windows と行末が混在しない。

### Windows 専用スクリプト

`.bat` ファイル（`start.bat`、`restart_service.bat` 等）は Mac では実行できない。開発中は不要なので無視してよい。

### OCR 機能（yomitoku）

`backend/services/novel_db/extractor.py` の OCR サブプロセスが使う Python は環境変数 `OCR_PYTHON` で設定する。

- **設定しない場合**: OCR 関連処理はエラーになるが、それ以外の機能は動作する
- **設定する場合**: Mac 上に yomitoku の venv を別途作成し、`OCR_PYTHON=/path/to/venv/bin/python` を `.env` に追記

yomitoku は CUDA 依存のため、Mac（GPU なし）では推論速度が非常に遅くなる点に注意。

### Linux 同期 / NSSM サービス

`LINUX_SYNC_ENABLED` はデフォルト無効。`setup_service.bat` / NSSM は Windows 専用のため Mac では使用しない。

---

## git 運用

Windows と Mac で同じリモートに push する場合、`.gitattributes` が行末を自動正規化するため特別な設定は不要。

```bash
git add <files>
git commit -m "..."
git push
```

Windows 側の `core.autocrlf=true` と Mac 側（デフォルト `input`）の差異は `.gitattributes` が吸収する。
