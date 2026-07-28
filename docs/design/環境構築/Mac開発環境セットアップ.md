# Mac 開発環境セットアップ

> status: living | last-verified: 2026-07-28

Windows をメイン環境として運用しつつ、Mac からコード編集・テスト実行・git 操作を行うための手順。

> **前提**: アプリの本番運用（NSSM サービス・Linux デプロイ）は Windows / Linux で行う。
> Macは現在も開発専用であり、ローカルLLM推論ホストとしての利用は
> [MacローカルLLM移行・比較計画](../../log/計画/MacローカルLLM移行・比較計画.md)の
> 受入完了後に限る。

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

# OCR worker を Mac で実行する場合のみ設定
# OCR_PYTHON=/Users/<user>/.venv/ocr/bin/python
# SURYA_INFERENCE_URL=http://<surya-host>:8768/v1

# データディレクトリ（省略時: <repo>/backend/data/）
# PIC2PDF_DATA_DIR=/Users/<user>/Documents/Pic2PDF

# Linux 同期は Mac では不要（デフォルト: 無効）
# LINUX_SYNC_ENABLED=false  ← コメントのままでよい
```

### 3. バックエンドセットアップ

```bash
# リポジトリルートで workspace 全体を同期
uv sync --group dev
```

ルート `.venv/` が生成される。`activate` は不要（`uv run` が自動検出）。

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

`.bat` ファイル（`scripts/start.bat`、`scripts/restart_service.bat` 等）は Mac では実行できない。開発中は不要なので無視してよい。

### OCR 機能（Surya 主系 / yomitoku 補助）

`backend/services/novel_db/extractor.py` の OCR サブプロセスが使う Python は
`OCR_PYTHON` で設定する。主系の Surya OCR 2 は
`SURYA_INFERENCE_URL` の OpenAI 互換 llama-server を呼び出す。

- **OCR を使わない場合**: OCR ジョブを投入しなければ、その他の開発・テストは動作する
- **リモート Surya を使う場合**: worker の依存を入れた Python を
  `OCR_PYTHON` に設定し、`SURYA_INFERENCE_URL` を到達可能なサーバーへ向ける
- **yomitoku 補助照合も使う場合**: `OCR_PACKAGE_PATH` が指す環境へ
  yomitoku と対応する PyTorch を別途用意する

Mac 上でのローカル Surya / yomitoku 実行は標準運用ではなく、
GPU・モデル互換性と推論時間を個別に検証する。通常の Mac 開発では
OCR を実行しないか、既存の Windows OCR agent / 推論サーバーを利用する。

### Linux 同期 / NSSM サービス

`LINUX_SYNC_ENABLED` はデフォルト無効。`setup_service.bat` / NSSM は Windows 専用のため Mac では使用しない。

---

## 将来のローカルLLM推論ホスト利用

M1 Max 64GBを小説RAGのLLM推論ホストとして使う案は計画中であり、
現時点の本番構成ではない。採否は、現行Qwen3.6-35B-A3B、Qwen3.6-27B Dense、
Gemma 4-31Bを同じ10巻入力で比較して決める。

- Macから本番DBを直接開かない。
- 推論APIをLANへ無認証公開しない。Linux本番へのSSH reverse tunnelを使う。
- 比較中の生成物は公開せず、監査スナップショットと全文差分を保存する。
- Mac停止やモデル不採用時はWindowsの現行推論環境へ戻す。
- Kindle撮影、OCR、検索索引構築はMac移行と独立して継続する。

環境構築、モデル候補、固定評価、受入条件、段階導入は
[MacローカルLLM移行・比較計画](../../log/計画/MacローカルLLM移行・比較計画.md)を正本とする。

---

## git 運用

Windows と Mac で同じリモートに push する場合、`.gitattributes` が行末を自動正規化するため特別な設定は不要。

```bash
git add <files>
git commit -m "..."
git push
```

Windows 側の `core.autocrlf=true` と Mac 側（デフォルト `input`）の差異は `.gitattributes` が吸収する。
