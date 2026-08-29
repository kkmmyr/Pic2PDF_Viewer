# Mac 開発環境セットアップ

> status: living | last-verified: 2026-08-29

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
cd frontend && npm run test
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

## 将来のローカルLLM推論ホスト利用

M1 Max 64GBを小説RAGのLLM推論ホストとして使う案は比較中であり、現時点の本番構成ではない。
候補はQwen3.8-27B Dense、現行Qwen3.6-35B-A3B、Qwen3.6-27B Dense、Gemma 4-31B、
Muse Glimmer 30B、Nemotron 3.5 Lightning 30B-A3Bである。2026-08-15までの初回比較では、
Qwen3.8を現行Qwen3.6の自動置換にせず、Qwen3.6をローカル系統の主生成器として維持する。
Museは短い根拠窓の高リスク主張に対する任意の第二検証候補とする。
Nemotronは短窓thinkingだけ合格したが、長文事実抽出の話者・場面・ページ根拠・人物名で不合格となり、
巻全体へ拡大していない。公開成果物の主生成はADR-0018のSol段階移行を優先する。

- Macから本番DBを直接開かない。
- 推論APIをLANへ無認証公開しない。Linux本番へのSSH reverse tunnelを使う。
- 比較中の生成物は公開せず、監査スナップショットと全文差分を保存する。
- QwenとMuseは64GBへ同時常駐できても同時生成しない。Qwenを停止してからMuseを起動し、
  Muse検証後に停止する。131,072 contextの同時常駐は空き約7%のため通常運用にしない。
- Museの初回試験時のOllama 0.30.11はvision projector非対応で推論できなかった。
  比較時だけ言語GGUFをHomebrew版`llama-server`へ渡し、`127.0.0.1`限定で起動する。
- Nemotron導入時にHomebrew Ollamaを0.32.9へ更新し、Qwen3.8の必須runtimeに合わせて
  0.32.12へ更新済みである。Nemotronの公式Q4_K_Mは25GB、
  32,768 contextで空きメモリ54%、swap 0だったが、比較用登録に留め、本番設定へ配線しない。
  Muse projectorの更新後runtime上の再試験は未実施なので、Museの運用経路は変更しない。
- Qwen3.8は`qwen3.8:27b`、Q4_K_M、17GB、context 262,144で追加登録済みである。
  10巻の同一プロンプトと`think=false`でQwen3.6と比較したが、完成要約に主体誤り、
  最終合意の欠落、途中切れが残った。人物事実抽出の反復崩壊は減ったが、巻全体は
  Qwen3.6の約31分22秒に対し約97分12秒だった。比較用登録に留め、本番既定値へ配線しない。
  途中切れに出力・context上限到達が含まれるため、完全不採用ではなく設定再評価待ちとする。
  保存済み事実表に対する局所A/Bのみ実行し、合格条件だけを巻全体へ拡大する。
- Qwen3.8のMac MLX比較経路として、生成を`mlx-dspark`の`127.0.0.1:11439`、
  bge-m3をEmbedding-only `mlx_vlm.server`の`127.0.0.1:11437`へ分離できる。
  M1 Max 64GBではQwen3.8 4bitのload、DFlash2、131,072 context・KV 8bit、短答、
  限定JSON、1024次元Embeddingまで疎通済みである。ただしこれはruntime確認であり、直前項の
  Ollama Q4_K_Mによる小説品質不合格を取り消さない。`.env`でのopt-in比較に限定し、
  applicationは永続生成jobを拒否してQAだけを許可する。Windows/Linux既定値と自動公開は変更しない。詳細は
  [ADR-0019](../基本設計/ADR/0019_apple-silicon-mlx-inference.md)と
  [GPU環境セットアップ](GPU環境セットアップ.md)を参照する。
- Mac停止やモデル不採用時はWindowsの現行推論環境へ戻す。
- Kindle撮影、OCR、検索索引構築はMac移行と独立して継続する。

現行の起動・切替手順は[GPU環境セットアップ](GPU環境セットアップ.md)、
過去の比較結果は[MacローカルLLM比較 完了記録](../../archive/検証/MacローカルLLM移行・比較_完了記録.md)を参照する。

---

## git 運用

Windows と Mac で同じリモートに push する場合、`.gitattributes` が行末を自動正規化するため特別な設定は不要。

```bash
git add <files>
git commit -m "..."
git push
```

Windows 側の `core.autocrlf=true` と Mac 側（デフォルト `input`）の差異は `.gitattributes` が吸収する。
