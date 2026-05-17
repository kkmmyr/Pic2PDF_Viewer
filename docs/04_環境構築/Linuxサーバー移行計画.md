# Linux サーバー移行計画

**ステータス**: 計画中（未着手）  
**作成日**: 2026-05-17  
**OS**: Ubuntu Server（LTS 推奨）  
**前提**: キャプチャ・OCR・LLM 推論は引き続き Windows で行い、Web アプリ（閲覧・検索・PDF 生成）を Linux サーバーに移行するハイブリッド構成。

---

## アーキテクチャ方針

```
Windows PC（現状維持）
  ├─ Kindle キャプチャ（kindle-pdf/）
  ├─ OCR / Embedding ビルド
  ├─ LLM 推論（llama.cpp / Ollama + Qwen）
  └─ バッチ完了後 ─→ rsync ────────────────┐
                                             ↓
                                        Linux サーバー
                                          ├─ FastAPI バックエンド（:8090）
                                          ├─ React フロントエンド（配信）
                                          └─ data/（すべてローカル）
                                               ├─ doujin/pdfs_compressed/ + thumbnails/
                                               ├─ comic/pdfs/ + thumbnails/
                                               ├─ novel/pdfs/ + thumbnails/
                                               ├─ meta.db（SQLite）
                                               └─ novel_db/（SQLite + LanceDB）
```

**データ種別ごとの管理方針:**

| データ | 保管場所 | Windows との関係 |
|---|---|---|
| PDF・サムネイル | Linux ローカル（master） | OCR/生成後に rsync で push |
| DB（SQLite + LanceDB） | Linux ローカル（master） | OCR/ビルド後に rsync で push |
| 生画像（`images/`） | Windows のみ | Linux には置かない（PDF 生成済みのため不要） |

生画像は PDF・サムネイル生成後は Linux 側に不要なため除外する。これによりストレージ使用量を大幅に削減できる。

---

## Phase A: パス・設定の外部化（必須・低コスト）

**目標**: コードを変えずに `.env` だけで Linux 上でも起動できる状態にする。

### A-1: `config/__init__.py` の Windows デフォルトパス除去

現状、以下 3 箇所がハードコードされた Windows パスをデフォルト値に持つ。

```python
# backend/config/__init__.py
AMAZON_DATA_DIR = os.environ.get("AMAZON_DATA_DIR", r"C:\Users\amashio\...")  # ← 変える
GEMMA_TOOL_DIR  = os.environ.get("GEMMA_TOOL_DIR",  r"D:\61.tool\Gemma 4")   # ← 変える
META_DB_BACKUP_DIR = os.environ.get("META_DB_BACKUP_DIR", r"C:\Users\...")    # ← 変える
```

変更方針: デフォルト値を `None` または空文字列に変え、値が設定されていない場合は機能を無効化する（AMAZON_DATA_DIR が未設定なら CSV インポートをスキップ等）。

### A-2: `pyproject.toml` の絶対パス除去

```toml
# backend/pyproject.toml
[tool.pytest.ini_options]
pythonpath = ["D:/61.tool/common/llm"]  # ← Windows 絶対パス
```

変更方針: `qwen-common` は `[tool.uv.sources]` で editable インストール済みなので `pythonpath` エントリ自体が不要な可能性が高い。削除して動作確認する。

### A-3: OCR サブプロセスのパス

`ocr_worker.py` / `extractor.py` 周辺で `Scripts/python.exe`（Windows）を参照している箇所を OS 判定で分岐。

```python
import sys, os
_venv = Path("...")  # 環境変数 OCR_VENV_DIR で上書き可
_python = _venv / ("Scripts" if sys.platform == "win32" else "bin") / "python"
```

または `OCR_PYTHON` という env 変数を 1 つ用意してパス全体を外部化する方が明快。

---

## Phase B: systemd サービス化（NSSM の代替）

**目標**: Linux で `restart_service.bat` 相当の運用ができる状態にする。

### B-1: systemd ユニットファイル作成

`deploy/pic2pdf-viewer.service` として管理：

```ini
[Unit]
Description=Pic2PDF Viewer
After=network.target

[Service]
Type=simple
User=<実行ユーザー>
WorkingDirectory=/opt/pic2pdf-viewer/backend
Environment=PIC2PDF_DATA_DIR=/opt/pic2pdf-viewer/data
ExecStart=/opt/pic2pdf-viewer/backend/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8091
Restart=on-failure
StandardOutput=append:/opt/pic2pdf-viewer/logs/service-stdout.log
StandardError=append:/opt/pic2pdf-viewer/logs/service-stderr.log

[Install]
WantedBy=multi-user.target
```

### B-2: 運用スクリプト作成

`restart_service.sh`（`restart_service.bat` の Linux 版）：

```bash
#!/bin/bash
sudo systemctl restart pic2pdf-viewer
sudo systemctl status pic2pdf-viewer --no-pager
echo "Tail logs: journalctl -u pic2pdf-viewer -f"
```

`build_release.sh`（`build_release.bat` の Linux 版）：

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")/frontend"
npm run build
echo "Build complete. Run ./restart_service.sh to reload."
```

---

## Phase C: 初回データ移行（Windows → Linux）

### C-1: rsync で全データをコピー

Linux サーバーをデータの master として、初回は Windows からすべてコピーする。  
生画像（`images/`）は PDF・サムネイル生成済みのため Linux 側には置かない。

```bash
# Windows（WSL または Git Bash から実行）
LINUX=user@linux-server
DEST=/opt/pic2pdf-viewer/data

# PDF・サムネイル
rsync -avz --progress backend/data/doujin/pdfs_compressed/ $LINUX:$DEST/doujin/pdfs_compressed/
rsync -avz --progress backend/data/doujin/thumbnails/      $LINUX:$DEST/doujin/thumbnails/
rsync -avz --progress backend/data/comic/pdfs/             $LINUX:$DEST/comic/pdfs/
rsync -avz --progress backend/data/comic/thumbnails/       $LINUX:$DEST/comic/thumbnails/
rsync -avz --progress backend/data/novel/pdfs/             $LINUX:$DEST/novel/pdfs/
rsync -avz --progress backend/data/novel/thumbnails/       $LINUX:$DEST/novel/thumbnails/

# DB
rsync -avz --progress backend/data/meta.db   $LINUX:$DEST/
rsync -avz --progress backend/data/novel_db/ $LINUX:$DEST/novel_db/
```

### C-2: Linux 側の `.env` 設定

```bash
# /opt/pic2pdf-viewer/.env
PIC2PDF_DATA_DIR=/opt/pic2pdf-viewer/data
META_DB_DIR=/opt/pic2pdf-viewer/data
NOVEL_DB_DIR=/opt/pic2pdf-viewer/data/novel_db

# Windows 専用機能は無効化（パスを設定しない）
# AMAZON_DATA_DIR=   （未設定 → CSV インポート無効）
# GEMMA_TOOL_DIR=    （未設定 → Gemma 連携無効）
# META_DB_BACKUP_DIR= （未設定 → バックアップ無効）
```

---

## Phase D: 継続運用（バッチ後の差分 push）

Windows でキャプチャ・OCR・PDF 生成を行うたびに、Linux へ差分を push する。  
`--delete` は不要（削除は手動で管理）。差分転送なので 2 回目以降は高速。

### D-1: push スクリプト（Windows 側）

`sync_to_linux.sh`（Git Bash / WSL から実行）として保存しておく：

```bash
#!/bin/bash
# 使い方: bash sync_to_linux.sh [doujin|comic|novel|all]
set -e
LINUX=user@linux-server
DEST=/opt/pic2pdf-viewer/data
TARGET=${1:-all}

sync_source() {
    local src=$1 dst=$2
    rsync -avz --progress "$src" "$LINUX:$dst"
}

if [[ $TARGET == "doujin" || $TARGET == "all" ]]; then
    sync_source backend/data/doujin/pdfs_compressed/ $DEST/doujin/pdfs_compressed/
    sync_source backend/data/doujin/thumbnails/      $DEST/doujin/thumbnails/
fi
if [[ $TARGET == "comic" || $TARGET == "all" ]]; then
    sync_source backend/data/comic/pdfs/       $DEST/comic/pdfs/
    sync_source backend/data/comic/thumbnails/ $DEST/comic/thumbnails/
fi
if [[ $TARGET == "novel" || $TARGET == "all" ]]; then
    sync_source backend/data/novel/pdfs/       $DEST/novel/pdfs/
    sync_source backend/data/novel/thumbnails/ $DEST/novel/thumbnails/
fi

# DB は常に同期（OCR/ビルド後は必ず実行）
sync_source backend/data/meta.db   $DEST/
sync_source backend/data/novel_db/ $DEST/novel_db/

echo "Sync complete."
```

使い方：
```bash
bash sync_to_linux.sh novel   # 小説だけ
bash sync_to_linux.sh all     # 全カテゴリ
```

### D-2: タイミングの目安

| 操作 | push のタイミング |
|---|---|
| Kindle キャプチャ → PDF 生成 | PDF 生成バッチ完了後 |
| OCR バッチ完了 | OCR 完了後（`novel_db/` が更新される） |
| 書誌メタ編集（タイトル・著者等） | 編集後に `meta.db` だけ push |
| 同人誌 ZIP → PDF 変換 | 変換バッチ完了後 |

**DB 転送中の競合について**: Linux 側が閲覧中でも SQLite の WAL モードなら読み取りは継続できる。手動 push 運用（バッチ完了後に実行）であれば問題ない。

---

## Phase D: LLM バックエンド対応（対象外）

Linux サーバーはスペック不足のため LLM 推論は対象外。小説 QA / サマリ生成機能は Linux サーバーでは利用しない。  
Windows 側で引き続き LLM を使う運用はそのまま維持する。

---

## Phase E: Ubuntu Server 24.04 インストール

詳細手順は別途用意した `INSTALL_GUIDE.md`（HP Spectre x360 向け）を参照。  
ポイントのみ抜粋:

- ディスク: `KXG50ZNV512G`（NVMe 512GB）を選択、LVM チェック外す
- **SSH サーバーは必ずインストール**（OpenSSH server を ON）
- インストール後の確認: `ip addr show` でローカル IP をメモ

インストール完了後、メイン PC から `d:\61.tool\Pic2PDF_Viewer` で Claude Code を開いて続きを進める。

---

## Phase F: インストール直後のサーバー初期設定

インストール完了・ログイン後、以下の順で進める。

### F-1: Tailscale 導入（リモートアクセス）

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

メイン PC でも Tailscale を有効化し、同じアカウントでログインすれば  
`ssh user@homeserver` で接続できるようになる（ローカル IP 不要）。

### F-2: VSCode Remote-SSH 接続確認

メイン PC の VSCode で Remote-SSH 拡張を使い `homeserver` に接続できることを確認。  
以降の作業はここから SSH 越しに行う。

### F-3: 必要パッケージのインストール

```bash
sudo apt update && sudo apt upgrade -y

# uv（Python パッケージ管理）
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# Node.js LTS
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs

# その他
sudo apt install -y git rsync
```

### F-4: アプリ配置

```bash
sudo mkdir -p /opt/pic2pdf-viewer
sudo chown $USER:$USER /opt/pic2pdf-viewer
cd /opt/pic2pdf-viewer

# ソースを Windows から転送（Git か rsync どちらか）
rsync -avz /d/61.tool/Pic2PDF_Viewer/ user@homeserver:/opt/pic2pdf-viewer/ \
  --exclude='.venv' --exclude='node_modules' --exclude='backend/data'

# Python 依存インストール
cd backend && uv sync

# フロントエンドビルド
cd ../frontend && npm ci && npm run build
```

### F-5: データディレクトリ作成・初回データ転送

```bash
# Linux 側でディレクトリ作成
mkdir -p ~/pic2pdf-data/{doujin/{pdfs_compressed,thumbnails},comic/{pdfs,thumbnails},novel/{pdfs,thumbnails},novel_db}
```

```bash
# Windows 側（WSL / Git Bash）から初回 rsync（Phase C-1 の実行）
bash sync_to_linux.sh all
```

### F-6: .env 配置

```bash
cat > /opt/pic2pdf-viewer/.env << 'EOF'
PIC2PDF_DATA_DIR=/home/<user>/pic2pdf-data
META_DB_DIR=/home/<user>/pic2pdf-data
NOVEL_DB_DIR=/home/<user>/pic2pdf-data/novel_db
# ALLOWED_ORIGINS は Caddy 設定後に更新
ALLOWED_ORIGINS=http://homeserver.tailnet-xxxx.ts.net:8090
EOF
```

### F-7: systemd ユニット有効化

```bash
sudo cp /opt/pic2pdf-viewer/deploy/pic2pdf-viewer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pic2pdf-viewer
sudo systemctl status pic2pdf-viewer
```

### F-8: nginx リバースプロキシ（静的ファイル高速化）

nginx を前段に置き、画像・サムネイル等の静的ファイルを Python を経由せず直接ディスクから配信する。
uvicorn は `127.0.0.1:8091`（ローカルのみ）に移動し、API リクエストのみを受け持つ。

```bash
sudo apt install -y nginx
```

設定ファイルをリポジトリから配置：

```bash
sudo cp /opt/pic2pdf-viewer/deploy/nginx-pic2pdf-viewer.conf \
        /etc/nginx/sites-available/pic2pdf-viewer
sudo ln -s /etc/nginx/sites-available/pic2pdf-viewer \
           /etc/nginx/sites-enabled/pic2pdf-viewer
# デフォルト設定を無効化（port 80 を占有している場合の競合を防ぐ）
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl enable --now nginx
```

systemd サービスも更新（uvicorn を 8091 ローカルに変更）：

```bash
sudo systemctl daemon-reload
sudo systemctl restart pic2pdf-viewer nginx
sudo systemctl status pic2pdf-viewer nginx --no-pager
```

動作確認：

```bash
curl -I http://localhost:8090/        # nginx 経由で index.html
curl -I http://localhost:8090/api/health  # uvicorn へのプロキシ
```

**ポート構成**:
- `:8090` — nginx（外部公開）
- `:8091` — uvicorn（localhost のみ、nginx からのみアクセス）

**キャッシュ設定**: 画像・アセットは `Cache-Control: public, immutable, max-age=2592000`（30日）。
HTML（index.html）は `no-cache`（デプロイ即反映）。

### F-9: ufw ファイアウォール設定

```bash
sudo ufw allow OpenSSH
# Caddy を使う場合
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
# Caddy なし・直接アクセスの場合のみ
# sudo ufw allow 8090/tcp
sudo ufw enable
```

---

## Phase G: ビルド・CI 対応（任意）

- GitHub Actions に Ubuntu ランナーでのバックエンドテストを追加（`uv run pytest`）
- Dockerfile は任意。uv + systemd 構成で十分運用可能

---

## 作業順序（推奨）

```
【Ubuntu インストール】INSTALL_GUIDE.md の手順を実行
    ↓
【コード修正】A-1（設定外部化）→ A-2（pythonpath 除去）→ A-3（OCR パス外部化）
    + B-1（systemd ユニット）→ B-2（運用スクリプト）
    + D-1（sync_to_linux.sh 作成）
    ↓ （Windows 側の準備完了）
【サーバー初期設定】F-1（Tailscale）→ F-2（VSCode Remote-SSH）→ F-3（パッケージ）
    ↓
【アプリ展開】F-4（ソース転送）→ F-5（初回データ rsync）→ F-6（.env）→ F-7（systemd）
    ↓ （この時点で Tailscale 経由で閲覧できる状態）
【任意】F-8（Caddy / HTTPS）→ G（CI 対応）
```

---

## 未解決事項・確認が必要な点

- `backend/utils/logger.py` の Windows ローテーション回避ロジックは Linux では不要だが、削除するか `sys.platform` で分岐するか
- `lancedb` の Linux 動作確認（基本的にクロスプラットフォームだが、Linux 側では読み取りのみなので問題は少ないはず）
- LanceDB インデックスは Windows で生成済みのファイルをそのまま rsync で持ち込む（Linux 側での再ビルド不要）
- Linux サーバーのストレージ容量見積もりが必要（PDF + サムネイル + DB の合計サイズ）
