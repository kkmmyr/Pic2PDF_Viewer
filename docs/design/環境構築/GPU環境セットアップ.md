# OCR・Embedding・ローカルLLM GPU環境セットアップ

> status: living | last-verified: 2026-08-22

本書は現在利用できる起動・切替手順だけを扱う。モデル比較の数値と不採用試験は
[GPU・モデル検証履歴](../../archive/検証/GPU環境セットアップ_検証履歴.md)および
[小説RAG 技術検証履歴](../../archive/検証/小説RAG_技術検証履歴.md)を参照する。

## 1. 実行基盤の分離

| 系統 | 通常運用 | 実行基盤 |
|---|---|---|
| Surya OCR 2 | OCR主系 | OpenAI互換`llama-server` + GGUF |
| yomitoku | 独立照合・後方互換 | Python + PyTorch CUDA |
| bge-m3 | Embedding | Ollama。MacはMLX FP16 + CLSを選択可 |
| Qwen | 主生成・QA | Windows/Linuxはllama-server、MacはMLXを選択可 |

Python依存はルートuv workspaceで管理し、初回はリポジトリルートで`uv sync`する。
GPUモデルとMLX runtimeは容量・platform依存が大きいためrepo外へ置く。

## 2. Surya OCR 2

管理画面`/novel/manage`からのOCRは既定で`OCR_ENGINE=surya2`を使う。

```dotenv
OCR_ENGINE=surya2
SURYA_INFERENCE_URL=http://127.0.0.1:8768/v1
SURYA_MODEL=surya-ocr-2
SURYA_MODEL_REVISION=<固定版識別子>

# workerがserverを自動起動する場合だけ設定
SURYA_LLAMA_SERVER_PATH=C:\path\to\llama-server.exe
SURYA_MODEL_PATH=D:\path\to\surya-ocr-2.gguf
SURYA_MMPROJ_PATH=D:\path\to\surya-2-mmproj.gguf
```

- 既存`SURYA_INFERENCE_URL`が応答する場合、3つのローカルpathは不要。
- 自動起動する場合は3つすべてを設定し、model/mmproj/llama.cpp revisionを運用記録へ残す。
- Linux本番の`OCR_AGENT_ENABLED=true`ではWindows OCR agentがjobをclaimする。
- 品質ゲートと公開条件は[OCR設計書](../詳細設計/機能別/OCR設計書.md)を正本とする。

## 3. yomitoku補助環境

```powershell
# リポジトリルート
uv sync --package pic2pdf-viewer-kindle --group gpu
uv run --package pic2pdf-viewer-kindle python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
```

`True`でない場合はNVIDIA driverとCUDA版PyTorchを確認する。backendの通常OCRが使う
`OCR_PYTHON` / `OCR_PACKAGE_PATH`の外部環境と、`kindle-pdf` GPU groupは別環境である。

## 4. bge-m3

Ollama既定:

```dotenv
NOVEL_DB_OLLAMA_BASE_URL=http://<ollama-host>:11434
NOVEL_DB_EMBED_BACKEND=ollama
NOVEL_DB_EMBED_NUM_GPU=0
```

リモートGPU使用時だけ`NOVEL_DB_EMBED_NUM_GPU=99`へ変更し、終了後は接続先とGPU値を
両方戻してbackendを再起動する。

Mac MLXではFP16重みを使い、モデルディレクトリの`1_Pooling/config.json`で
`pooling_mode_cls_token=true`、`pooling_mode_mean_tokens=false`を固定する。
切替前に1024次元、既存Ollamaとの同一文cosine 0.9999以上、旧新交差Top-10一致を確認する。

## 5. Apple Silicon MLX

M1 Max 64GBで確認した採用構成は、Qwen3.6 35B-A3Bとbge-m3をMLX、Gemma 4 12Bを
Ollamaで実行する構成である。詳細な採否は[ADR-0019](../基本設計/ADR/0019_apple-silicon-mlx-inference.md)を参照する。

MLX runtimeはrepo外の専用venvへ隔離する。

```bash
uv venv --python 3.12 /path/to/pic2pdf-mlx/.venv
uv pip install --python /path/to/pic2pdf-mlx/.venv/bin/python mlx-vlm==0.6.15 huggingface_hub

/path/to/pic2pdf-mlx/.venv/bin/hf download mlx-community/Qwen3.6-35B-A3B-4bit \
  --revision 38740b847e4cb78f352aba30aa41c76e08e6eb46 \
  --local-dir /path/to/pic2pdf-mlx/models/qwen3.6-35b-a3b-4bit
/path/to/pic2pdf-mlx/.venv/bin/hf download mlx-community/bge-m3-mlx-fp16 \
  --revision a37eddded9a6a1273a87fb8b0da0d1cdbd98aeec \
  --local-dir /path/to/pic2pdf-mlx/models/bge-m3-fp16
```

起動:

```bash
/path/to/pic2pdf-mlx/.venv/bin/mlx_vlm.server \
  --host 127.0.0.1 \
  --port 11437 \
  --model /path/to/pic2pdf-mlx/models/qwen3.6-35b-a3b-4bit \
  --embedding-model /path/to/pic2pdf-mlx/models/bge-m3-fp16 \
  --max-num-seqs 1
```

Macの`.env`:

```dotenv
NOVEL_DB_MLX_BASE_URL=http://127.0.0.1:11437
NOVEL_DB_LLM_BACKEND=mlx
NOVEL_DB_LLM_MODEL=/path/to/pic2pdf-mlx/models/qwen3.6-35b-a3b-4bit
NOVEL_DB_GEMMA_BACKEND=ollama
NOVEL_DB_CHAR_EXTRACT_MODEL=gemma4:12b
NOVEL_DB_CONTEXT_MODEL=gemma4:12b
NOVEL_DB_QA_EXPAND_MODEL=gemma4:12b
NOVEL_DB_EMBED_BACKEND=mlx
NOVEL_DB_EMBED_MODEL=/path/to/pic2pdf-mlx/models/bge-m3-fp16
```

`/health`、生成短答、限定JSON、Embedding 1024次元を確認する。異なる生成モデルを
同じcacheで同時実行しない。Windows/Linux既定値と公開データはMac切替で変更しない。

## 6. Qwen3.8比較経路

Qwen3.8-27Bの`mlx-dspark`は`127.0.0.1:11439`、bge-m3は`11437`へ分離する。
この経路はQA・比較専用で、`full_build`、`generate_relations`、自動公開へ使用しない。
transport smoke合格は既存の小説品質不合格を取り消さない。

Nemotron 75B/30B、Ornith 35B-A3B、Gemma MLXの再現手順は現行運用ではないため、
[検証履歴](../../archive/検証/GPU環境セットアップ_検証履歴.md)へ移した。

## 7. トラブルシューティング

### OCR jobがclaimされない

- Linux本番の`OCR_AGENT_ENABLED`
- Windows OCR agentのheartbeat
- agent tokenとAPI URL

### Surya serverへ接続できない

- `SURYA_INFERENCE_URL`の`/models`
- 自動起動用3 path
- `nvidia-smi`と他processのGPU占有

### yomitokuでCUDAを利用できない

- PyTorch versionが`+cu121`か
- `kindle-pdf/pyproject.toml`の`pytorch-cu121` sourceが適用されたか

CUDA/PyTorchを変更するときは、yomitoku実機比較とsecurity allowlistを同じ変更で確認する。

## 関連文書

- [uv環境セットアップ](uv環境セットアップ.md)
- [Mac開発環境セットアップ](Mac開発環境セットアップ.md)
- [OCR設計書](../詳細設計/機能別/OCR設計書.md)
- [小説RAG パイプライン設計](../詳細設計/機能別/小説RAG_パイプライン設計.md)
- [小説RAG 現行技術知見](../../log/技術知見/小説RAG_技術知見.md)
