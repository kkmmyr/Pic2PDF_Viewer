# OCR・Embedding GPU 環境セットアップ

> status: living | last-verified: 2026-07-27

小説処理で GPU を使う箇所は、主系 OCR、補助 OCR、Embedding の
3 系統に分かれる。依存環境と設定を混同しないこと。

| 系統 | 通常運用 | 実行基盤 |
|---|---|---|
| Surya OCR 2 | OCR 主系 | OpenAI 互換 `llama-server` + GGUF |
| yomitoku | 独立照合・比較・後方互換 | Python + PyTorch CUDA |
| bge-m3 | チャンク・サマリ Embedding | Ollama |

## 1. 共通前提

- NVIDIA GPU と対応ドライバが導入済み
- `nvidia-smi` が成功する
- Python 依存はリポジトリルートの uv workspace で管理する
- 初回はリポジトリルートで `uv sync` を実行する

uv workspace の正本はルート `pyproject.toml` と `uv.lock` であり、
`.venv/` もリポジトリルートに作られる。詳細は
[ADR-0010](../基本設計/ADR/0010_uv-workspace-monorepo.md) と
[uv 環境セットアップ](uv環境セットアップ.md) を参照。

## 2. Surya OCR 2（主系）

管理画面 `/novel/manage` から投入した OCR ジョブは、既定で
`OCR_ENGINE=surya2` を使う。Surya は PyTorch の
`kindle-pdf` GPU group ではなく、OpenAI 互換の
`llama-server` を通じて実行する。

主な環境変数:

```dotenv
OCR_ENGINE=surya2
SURYA_INFERENCE_URL=http://127.0.0.1:8768/v1
SURYA_MODEL=surya-ocr-2
SURYA_MODEL_REVISION=<model/mmproj/llama.cpp の固定版識別子>

# 既存サーバーへ到達できない場合に worker が自動起動するための設定
SURYA_LLAMA_SERVER_PATH=C:\path\to\llama-server.exe
SURYA_MODEL_PATH=D:\path\to\surya-ocr-2.gguf
SURYA_MMPROJ_PATH=D:\path\to\surya-2-mmproj.gguf
```

- `SURYA_INFERENCE_URL` に既存サーバーが応答する場合、3 つのローカルパスは不要。
- worker に自動起動させる場合は、3 つのパスをすべて設定する。
- モデルと実行ファイルの実パス・固定版識別子は環境固有なので、
  `.env` と運用記録で管理し、設計書へ端末固有値を固定しない。
- Linux 本番で `OCR_AGENT_ENABLED=true` の場合、OCR は Windows agent が
  claim する。Linux 本番だけで GPU 推論が完結する構成ではない。

実行条件、品質ゲート、モデル版監査は
[OCR 設計書](../詳細設計/機能別/OCR設計書.md) を正本とする。

## 3. yomitoku（補助・互換系）

`kindle-pdf/pyproject.toml` の `gpu` dependency group は、
yomitoku と CUDA 12.1 版 PyTorch を含む。主系 Surya の実行には不要だが、
yomitoku の診断・比較を `kindle-pdf` 環境で行う場合に使用できる。

```powershell
# リポジトリルートで実行
uv sync --package pic2pdf-viewer-kindle --group gpu
uv run --package pic2pdf-viewer-kindle python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
```

`True` が返らない場合は NVIDIA ドライバと、インストールされた
PyTorch が `+cu121` かを確認する。

通常の backend OCR で行う yomitoku 独立照合は、
`OCR_PYTHON` / `OCR_PACKAGE_PATH` が指す外部 OCR 環境を使用する。
リポジトリの `kindle-pdf` GPU group と外部 OCR 環境は同一ではない。

## 4. bge-m3 Embedding（Ollama）

Embedding は `NOVEL_DB_OLLAMA_BASE_URL` の Ollama を使用する。
CPU 運用の既定は `NOVEL_DB_EMBED_NUM_GPU=0`。GPU を使う場合は
接続先だけでなく `NOVEL_DB_EMBED_NUM_GPU` も変更する。

```dotenv
NOVEL_DB_OLLAMA_BASE_URL=http://<ollama-host>:11434
NOVEL_DB_EMBED_NUM_GPU=99
```

リモート GPU は処理中だけ使用し、終了後は通常の接続先と
`NOVEL_DB_EMBED_NUM_GPU=0` へ戻してバックエンドを再起動する。
片方だけを変更すると、リモートへ接続できても CPU 推論のままになる。

## 5. トラブルシューティング

### OCR ジョブが claim されない

- Linux 本番の `OCR_AGENT_ENABLED`
- Windows OCR agent の heartbeat
- agent token と API URL

を確認する。

### Surya server に接続できない

- `SURYA_INFERENCE_URL` の `/models` が応答するか確認
- 自動起動構成なら `SURYA_LLAMA_SERVER_PATH`、
  `SURYA_MODEL_PATH`、`SURYA_MMPROJ_PATH` の 3 件を確認
- `nvidia-smi` で他プロセスの GPU 占有を確認

### yomitoku で CUDA が利用できない

- `uv run --package pic2pdf-viewer-kindle python -c "import torch; print(torch.__version__, torch.cuda.is_available())"`
- バージョンが `+cpu` の場合は `kindle-pdf/pyproject.toml` の
  `pytorch-cu121` source が適用されたか確認

CUDA / PyTorch の組み合わせを変更する場合は、yomitoku の実機比較と
セキュリティ allowlist の再確認を伴うため、依存更新だけを単独で行わない。

## 関連ドキュメント

- [uv 環境セットアップ](uv環境セットアップ.md)
- [OCR 設計書](../詳細設計/機能別/OCR設計書.md)
- [小説 RAG パイプライン設計](../詳細設計/機能別/小説RAG_パイプライン設計.md)
- [ADR-0010: uv workspace](../基本設計/ADR/0010_uv-workspace-monorepo.md)
