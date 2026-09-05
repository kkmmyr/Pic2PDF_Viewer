# Mac 開発環境セットアップ

> status: living | last-verified: 2026-09-05

Windows をメイン環境として運用しつつ、Mac からコード編集・テスト実行・git 操作を行うための手順。

> **前提**: アプリの本番運用（NSSM サービス・Linux デプロイ）は Windows / Linux で行う。
> Macは本番配信端末ではないが、受入済みのQwen3.6・bge-m3 MLX構成を
> ローカルLLM推論ホストとして利用できる。現在の採用範囲は
> [ADR-0019](../基本設計/ADR/0019_apple-silicon-mlx-inference.md)を参照する。

---

## 前提条件

| ツール | インストール方法 | 確認コマンド |
|---|---|---|
| Homebrew | `https://brew.sh` | `brew --version` |
| uv (Python 管理) | `brew install uv` | `uv --version` |
| Node.js 22.x + npm 10.x | `.node-version`を読めるversion manager | `node --version && npm --version` |
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
npm ci
```

CIと同じルート`.node-version`のNode.js 22と、`frontend/package.json`の
`packageManager`に記録したnpm 10を使う。`npm install`は依存を意図して更新し、
`package.json`と`package-lock.json`を同じcommitで変更するときだけ実行する。
通常のセットアップで`npm ci`が失敗した場合は`npm install`で回避せず、
lockfileの再現性不具合として扱う。

Node.js 26では、Node組込みのexperimental Web StorageとVitestのjsdomが競合し、
`localStorage` / `sessionStorage`利用testが一括失敗することを2026-08-22に確認した。
製品回帰ではないため、通常検証はNode.js 22へ戻して実行する。

---

## 動作確認

### テスト実行

```bash
# バックエンド
cd backend && uv run pytest -q

# KindleのOS非依存ロジックとWindows境界のモック契約
cd ../kindle-pdf && uv run pytest -q

# フロントエンド
cd ../frontend && npm run test
```

Kindle testはmacOSでも収集・実行する。Windows API、UI Automation、
PyAutoGUIの実呼び出しは共通プラットフォーム境界で遅延し、testでは
決定的な代替実装へ差し替える。これはWindows実機受入の代替ではない。
Macで実機APIを直接呼ぶとプラットフォーム非対応エラーで安全に停止し、
Kindle接続・ウィンドウ前面化・全ページ撮影は引き続きWindowsの
ロック解除済み端末で確認する。

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
  MPS対応済みのyomitoku（v0.11.0以降）とPyTorchを別途用意し、
  `OCR_YOMITOKU_DEVICE=mps`を指定する。`kindle-pdf`の`gpu` groupはMac上で
  CUDA wheelではなくApple Silicon用PyTorchを解決する。

Mac 上でのローカル Surya 実行は標準運用ではなく、yomitokuは独立照合・比較・
後方互換用の補助経路として扱う。MPSの演算子fallbackを含むGPU・モデル互換性と推論時間を
個別に検証する。通常の Mac 開発では
OCR を実行しないか、既存の Windows OCR agent / 推論サーバーを利用する。

OwlOCR、ABBYY FineReader、Prizmo 等を本番主系とは独立した第二 OCR・
目視確認に利用する将来評価は
[Mac OCR 補助確認設計](../詳細設計/機能別/Mac_OCR補助確認設計.md)に従う。
これらの結果だけで `novel.db` へ公開・索引化しない。

### Linux 同期 / NSSM サービス

`LINUX_SYNC_ENABLED` はデフォルト無効。`setup_service.bat` / NSSM は Windows 専用のため Mac では使用しない。

---

## ローカルLLM推論ホストの境界

Mac MLXは明示的なopt-inによる対話QAの比較経路として扱う。永続生成jobは拒否し、通常のWindows/Linux設定や公開成果物を自動で置き換えない。採用契約は[ADR-0019](../基本設計/ADR/0019_apple-silicon-mlx-inference.md)、起動・切替手順は[GPU環境セットアップ](GPU環境セットアップ.md)を参照する。

Macから本番DBを直接開かず、推論APIはlocalhostとSSH reverse tunnelで接続する。比較生成物は公開せず、監査用の出力を保存する。Kindle撮影、OCR、検索索引構築とは独立して運用する。
過去のモデル比較、実測値、当時のruntime導入状況は[追加実測履歴](../../archive/検証/環境構築_追加実測履歴_2026-09-05.md)へ分離した。

---

## git 運用

Windows と Mac で同じリモートに push する場合、`.gitattributes` が行末を自動正規化するため特別な設定は不要。

```bash
git add <files>
git commit -m "..."
git push
```

Windows 側の `core.autocrlf=true` と Mac 側（デフォルト `input`）の差異は `.gitattributes` が吸収する。
