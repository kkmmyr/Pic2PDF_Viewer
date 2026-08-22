# OCR・Embedding GPU 環境セットアップ

> frozen: 2026-08-22 | role: 比較モデルを含む過去の再現手順・実測記録
>
> 現行手順は[GPU環境セットアップ](../../design/環境構築/GPU環境セットアップ.md)を参照する。

> status: living | last-verified: 2026-08-21

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

## 4. bge-m3 Embedding（Ollama / MLX）

Embeddingの既定は`NOVEL_DB_OLLAMA_BASE_URL`のOllamaである。
CPU運用の既定は`NOVEL_DB_EMBED_NUM_GPU=0`。OllamaでGPUを使う場合は
接続先だけでなく`NOVEL_DB_EMBED_NUM_GPU`も変更する。

```dotenv
NOVEL_DB_OLLAMA_BASE_URL=http://<ollama-host>:11434
NOVEL_DB_EMBED_NUM_GPU=99
```

リモート GPU は処理中だけ使用し、終了後は通常の接続先と
`NOVEL_DB_EMBED_NUM_GPU=0` へ戻してバックエンドを再起動する。
片方だけを変更すると、リモートへ接続できても CPU 推論のままになる。

Apple Siliconでは§5のMLXへ切替できる。MLX版bge-m3は
`1_Pooling/config.json`をCLS poolingへ固定しなければ既存Ollama索引と
別のベクトル空間になるため、設定なしのmean poolingを使用しない。

## 5. Apple Silicon MLX（任意）

M1 Max 64GBで検証した構成。MLX runtimeとモデルはuv workspaceへ追加せず、
repo外の専用venvに隔離する。現行のEmbedding対応版は`mlx-vlm==0.6.15`である。

```bash
uv venv --python 3.12 /path/to/pic2pdf-mlx/.venv
uv pip install --python /path/to/pic2pdf-mlx/.venv/bin/python mlx-vlm==0.6.13 huggingface_hub

/path/to/pic2pdf-mlx/.venv/bin/hf download mlx-community/Qwen3.6-35B-A3B-4bit \
  --revision 38740b847e4cb78f352aba30aa41c76e08e6eb46 \
  --local-dir /path/to/pic2pdf-mlx/models/qwen3.6-35b-a3b-4bit
/path/to/pic2pdf-mlx/.venv/bin/hf download mlx-community/gemma-4-12B-4bit \
  --revision 7d7c99c4d1b1d2ec2b52e2c46821cef2fa22ce0c \
  --local-dir /path/to/pic2pdf-mlx/models/gemma-4-12b-4bit
/path/to/pic2pdf-mlx/.venv/bin/hf download mlx-community/bge-m3-mlx-fp16 \
  --revision a37eddded9a6a1273a87fb8b0da0d1cdbd98aeec \
  --local-dir /path/to/pic2pdf-mlx/models/bge-m3-fp16
```

Gemmaの取得は比較再現用であり、2026-08-17の品質ゲートでは不採用である。
通常運用ではGemmaのOllama登録を維持する。

`/path/to/pic2pdf-mlx/models/bge-m3-fp16/1_Pooling/config.json`を次の内容で作成する。

```json
{
  "word_embedding_dimension": 1024,
  "pooling_mode_cls_token": true,
  "pooling_mode_mean_tokens": false,
  "pooling_mode_max_tokens": false,
  "pooling_mode_mean_sqrt_len_tokens": false,
  "pooling_mode_weightedmean_tokens": false,
  "pooling_mode_lasttoken": false,
  "include_prompt": true
}
```

serverは外部公開せず、同時生成数を1へ制限する。採用構成ではQwenを起動時に、
bge-m3を別embedding cacheへpreloadし、MLXへ不採用のGemmaは要求しない。
将来の再評価でGemmaを要求した場合だけ、同じtext-generation cacheのQwenがunloadされる。

```bash
/path/to/pic2pdf-mlx/.venv/bin/mlx_vlm.server \
  --host 127.0.0.1 \
  --port 11437 \
  --model /path/to/pic2pdf-mlx/models/qwen3.6-35b-a3b-4bit \
  --embedding-model /path/to/pic2pdf-mlx/models/bge-m3-fp16 \
  --max-num-seqs 1
```

Macの`.env`だけを次のように切り替える。Qwenとbge-m3をMLX、GemmaをOllamaにする
実機採用構成であり、Windows/Linuxの既定値は変更しない。

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

`curl http://127.0.0.1:11437/health`の成功、embedding 1024次元、既存Ollama
embeddingとの同一文cosine 0.9999以上、旧/新交差Top-10一致を確認してから切り替える。
将来Gemmaを再評価して`NOVEL_DB_GEMMA_BACKEND=mlx`にする場合、Qwen/Gemmaは
同じ生成cacheを使うため、モデルが異なるリクエストを同時実行しない。

### 5.1 Qwen3.8-27B + `mlx-dspark`（MacのMLX寄せ・比較用）

Qwen3.8-27BをMLX 4bitで使う場合、生成は`mlx-dspark`へ分離する。
`mlx-dspark`はMiaAI LabのDGX Spark用SGLang recipeではなく、Apple Silicon上で
MLX重みを推測デコードするコミュニティruntimeである。runtimeとQwen3.8は既存の
`mlx_vlm`用venvへ混ぜず、専用venv・専用ポートへ置く。

```bash
uv venv --python 3.12 /path/to/pic2pdf-mlx/runtimes/mlx-dspark/.venv
uv pip install --python /path/to/pic2pdf-mlx/runtimes/mlx-dspark/.venv/bin/python \
  mlx-dspark==0.15.1 mlx-lm==0.31.3 mlx-vlm==0.6.15 huggingface_hub

/path/to/pic2pdf-mlx/runtimes/mlx-dspark/.venv/bin/hf download \
  mlx-community/Qwen3.8-27B-4bit \
  --local-dir /path/to/pic2pdf-mlx/models/qwen3.8-27b-4bit
```

`mlx-dspark`はEmbedding endpointを持たないため、bge-m3だけを既存venvの
`mlx_vlm.server`で11437へ起動し、Qwen3.8の生成を11439へ起動する。Qwen3.6の重みを
11437へ同時にロードしない。

```bash
# Embedding-only server（既存venv）
/path/to/pic2pdf-mlx/.venv/bin/mlx_vlm.server \
  --host 127.0.0.1 \
  --port 11437 \
  --embedding-model /path/to/pic2pdf-mlx/models/bge-m3-fp16 \
  --log-level INFO

# Qwen3.8 generation server（専用venv）
/path/to/pic2pdf-mlx/runtimes/mlx-dspark/.venv/bin/mlx-dspark serve \
  --host 127.0.0.1 \
  --port 11439 \
  --model /path/to/pic2pdf-mlx/models/qwen3.8-27b-4bit \
  --mode auto \
  --no-thinking \
  --max-batch 1 \
  --default-max-tokens 8192 \
  --context-window 131072 \
  --kv-bits 8
```

Macの`.env`は次のようにする。`NOVEL_DB_MLX_BASE_URL`はEmbedding専用、
`NOVEL_DB_MLX_DSPARK_BASE_URL`はQwen生成専用で、Windows/Linuxの既定値は変更しない。

```dotenv
NOVEL_DB_MLX_BASE_URL=http://127.0.0.1:11437
NOVEL_DB_MLX_DSPARK_BASE_URL=http://127.0.0.1:11439
NOVEL_DB_LLM_BACKEND=mlx_dspark
NOVEL_DB_LLM_MODEL=/path/to/pic2pdf-mlx/models/qwen3.8-27b-4bit
NOVEL_DB_GEMMA_BACKEND=ollama
NOVEL_DB_CHAR_EXTRACT_MODEL=gemma4:12b
NOVEL_DB_CONTEXT_MODEL=gemma4:12b
NOVEL_DB_QA_EXPAND_MODEL=gemma4:12b
NOVEL_DB_EMBED_BACKEND=mlx
NOVEL_DB_EMBED_MODEL=/path/to/pic2pdf-mlx/models/bge-m3-fp16
```

初期値は`context-window=131072`、KV cache 8bit、同時生成1とする。起動後に
`curl http://127.0.0.1:11439/health`、`curl http://127.0.0.1:11437/health`、
Embedding 1024次元を確認する。`mlx-dspark`は`response_format`を解釈しないため、
`format="json"`を指定するJSON objectタスクは共通LLMの限定adapterが自然停止・JSON形式を検査する。
JSON配列を要求する関係抽出はこのadapterの対象外である。Qwen3.8の固定小説品質ゲート合格までは、
Macでの比較・QA用途に限定する。applicationは`full_build` / `generate_relations`と、
`NOVEL_DB_GEMMA_BACKEND=qwen`時の`generate_contexts`をjob開始前に拒否し、自動公開へ接続しない。

2026-08-22のM1 Max 64GB実機では、上記version構成に`mlx 0.32.1`と
`transformers 5.15.1`が解決され、Qwen3.8 target約15GB、DFlash2 cache約3.6GBとなった。
初回の`--mode auto`はdrafterを取得し、Metal kernelを一度calibrationしてから
`mode=dflash`で待受を開始する。起動ログが`loading auto engine`で止まって見えても、
drafterの`.incomplete`が増加中なら中断せず待つ。待受後の`/health`では少なくとも
`status=ok`、`mode=dflash`、`context_window=131072`、`kv_bits=8`、
`thinking_default=off`、memory guard正常を確認する。

同実機では短答`1+1 -> 2`、共通Backendの限定JSON adapterで`{"answer":2}`、
`embed_batch`で1件・1024次元を確認した。これは起動・API・形式契約のsmoke testであり、
Qwen3.8の小説品質ゲート合格を意味しない。品質比較時は短答のtoken/sを性能値として採用せず、
固定小説fixtureの入力・出力token、TTFT、decode時間、完了理由を保存する。

### 5.2 Nemotron Labs 3 Puzzle 75B（比較用・排他起動）

`Nemotron-Labs-3-Puzzle-75B-A9B`は75.3B total / 9.3B activeの
Mamba 2・Attention・LatentMoE混成モデルである。64GB Macではuniform 6bit版ではなく、
routed expertを4bit、dense/shared expertとembeddingを6bit、出力headをBF16にした
community変換を使う。配布物は45,104,722,602 bytes（42.007GiB）で、配布者の
M2 Max 64GB実測はMLX peak 49.6835GB / process RSS 45.3008GBである。

通常の`mlx-lm 0.31.x`は層ごとに異なるexpert幅とactive expert数を扱えない。
upstreamへ未統合のPuzzle対応branchを固定commitで専用venvへ隔離し、既存Qwen / bge-m3用
`mlx-vlm`環境へ上書きしない。branch差分はNemotron-H、SSM、model remapping、単体testだけを
対象とし、導入前に差分を監査する。

```bash
git clone --branch feat/nemotron-h-puzzle-support \
  https://github.com/sxuff/mlx-lm.git \
  /path/to/pic2pdf-mlx/runtimes/mlx-lm-nemotron-puzzle
git -C /path/to/pic2pdf-mlx/runtimes/mlx-lm-nemotron-puzzle \
  checkout 0f88e16

uv venv --python 3.12 \
  /path/to/pic2pdf-mlx/runtimes/mlx-lm-nemotron-puzzle/.venv
uv pip install \
  --python /path/to/pic2pdf-mlx/runtimes/mlx-lm-nemotron-puzzle/.venv/bin/python \
  -e /path/to/pic2pdf-mlx/runtimes/mlx-lm-nemotron-puzzle \
  huggingface-hub

/path/to/pic2pdf-mlx/runtimes/mlx-lm-nemotron-puzzle/.venv/bin/hf download \
  tekosML/Nemotron-Labs-3-Puzzle-75B-A9B-MLX-4bit-experts-6bit \
  --revision 695829721099e64aeaae22fa2f81d7740815a49e \
  --local-dir /path/to/pic2pdf-mlx/models/nemotron-puzzle-75b-a9b-mixed-4-6bit
```

モデルrepo内のTransformers向けcustom Pythonは実行せず、`--trust-remote-code`も付けない。
固定branchの`MODEL_REMAPPING`から組み込み`nemotron_h`実装へ読み替える。

Qwen / bge-m3 serverを停止し、Nemotronを単独でlocalhostへ起動する。比較用portは
`11438`とし、同時生成を1、prompt cacheを0へ制限する。model card推奨samplingは
`temperature=1.0 / top_p=0.95`である。事実抽出の再現試験ではrequestごとの値も保存する。

```bash
/path/to/pic2pdf-mlx/runtimes/mlx-lm-nemotron-puzzle/.venv/bin/mlx_lm.server \
  --host 127.0.0.1 \
  --port 11438 \
  --model /path/to/pic2pdf-mlx/models/nemotron-puzzle-75b-a9b-mixed-4-6bit \
  --temp 1.0 \
  --top-p 0.95 \
  --max-tokens 4096 \
  --chat-template-args '{"enable_thinking":false}' \
  --decode-concurrency 1 \
  --prompt-concurrency 1 \
  --prompt-cache-size 0 \
  --prompt-cache-bytes 0

curl http://127.0.0.1:11438/health
```

実機では`/path/to/pic2pdf-mlx/switch-mlx-server.sh nemotron`でQwen / bge-m3を停止して
Nemotronをforeground起動し、評価後は同scriptへ`qwen`を渡して元へ戻せる。scriptは既知の
11437 / 11438 listenerだけを停止し、未知processがportを使っている場合はfail closedにする。

2026-08-17のM1 Max 64GB実測では、9個のsafetensorsと`tokenizer.json`が配布元SHA-256へ
すべて一致し、固定branchのPuzzle単体testは12件合格した。Qwen / bge-m3を停止し、別用途の
ComfyUIは停止しない条件でも`/health`、短答、既存`LlamaServerBackend`のstreamingが成功した。
warm短答は1.564秒だった。一方、初回ロード中はsystem-wide swapが8.74GBから最大33.79GBへ
増え、空きメモリ指標は最小9%となった。64GBへロードできるが、他のML workloadと併用する運用には
余裕がない。

茉莉花官吏伝10巻74〜75ページの固定ケースは、non-thinkingが134.142秒で最終合意を
「牢へ戻る」と誤判定した。thinkingは187.346秒で2,048 token上限まで`OCR`を反復して最終JSONを
返さず、`low_effort`も48.073秒で同じ誤判定とenum違反になった。早期品質ゲート不合格のため、
32,768 token試験、巻全体要約、本番設定への配線には進まない。評価後はNemotronを停止し、
Qwen / bge-m3 serverのhealth、短答、1,024次元embeddingを再確認して復旧した。

`mlx_lm.server`は`chat_template_kwargs`、既存の`mlx_vlm.server`はトップレベル
`enable_thinking`を使うため、同じAPI互換とみなして本番設定へ直結しない。短窓・長文・
JSON終端の品質ゲートを通るまでは比較用に限定し、停止後は
`/path/to/pic2pdf-mlx/start-server.sh`でQwen / bge-m3構成へ戻す。Ollamaの
`nemotron-3.5-lightning:30b-a3b-q4_K_M`は別モデルなので削除・上書きしない。
requestの`model`には短縮名ではなく起動時と同じローカル絶対pathを渡す。未知の名前は
Hugging Face上の別モデルとして解決されるため、localhost client側でも固定値にする。

30Bのstock `mlx-lm 0.31.3`では、prompt cache有効時に無関係な後続promptへ
直前回答の一部を返す汚染を再現した。Puzzle用feature branchで同じ事象は未再現だが、
Mamba/SSM hybridの再評価では安全側に倒してcacheを無効化する。2026-08-17のPuzzle実測は
cache 1で取得した記録なので、将来runtime更新後に再試験する場合はcache 0から取り直す。

### 5.3 Nemotron 3.5 Lightning 30B（比較用・MLX不採用）

75Bより小さい30B-A3Bは既存Qwen / bge-m3用venvの`mlx-lm 0.31.3`でロードできる。
4bit版と6bit版を固定revisionで取得し、配布元SHA-256と照合する。Hugging Face Xet経路が
0 byteのまま停滞する場合は、未完了ファイルを残して通常HTTPへ再開できる。

`bash
HF_HUB_DISABLE_XET=1 /path/to/pic2pdf-mlx/.venv/bin/hf download \
  mlx-community/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit \
  --revision 55ac8c89261109b36c04371cd3f479a4594208c8 \
  --local-dir /path/to/pic2pdf-mlx/models/nemotron-3.5-lightning-30b-a3b-4bit

HF_HUB_DISABLE_XET=1 /path/to/pic2pdf-mlx/.venv/bin/hf download \
  Vontra/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-MLX-6bit \
  --revision bd2a75d36c78b83bd89dd7c7a26916116c54fecd \
  --local-dir /path/to/pic2pdf-mlx/models/nemotron-3.5-lightning-30b-a3b-6bit
`

4bitは17,775,339,392 bytes、6bitは25,667,608,448 bytesである。両方ともBF16由来の
affine group 64で、設定とchat templateの差は4 / 6bitだけである。checkpointに
custom Pythonはなく、`--trust-remote-code`は使わない。MLX実装は`mtp.*`を
除外するため、Ollama登録の`draft_num_predict=2`相当は利用できない。

比較serverは別port `11439`へ単独起動し、Nemotron-Hではprompt cacheを必ず無効にする。

`bash
/path/to/pic2pdf-mlx/.venv/bin/mlx_lm.server \
  --host 127.0.0.1 \
  --port 11439 \
  --model /path/to/pic2pdf-mlx/models/nemotron-3.5-lightning-30b-a3b-6bit \
  --temp 1.0 \
  --top-p 0.95 \
  --max-tokens 8192 \
  --chat-template-args '{"enable_thinking":false}' \
  --decode-concurrency 1 \
  --prompt-concurrency 1 \
  --prompt-cache-size 0 \
  --prompt-cache-bytes 0
`

M1 Max 64GBでは4bitが約16.9GiB、6bitが約24GBのfootprintでロードできる。
74〜75ページ固定ケースは、4bit thinkingが3/3誤答、6bit thinkingが8,192 token上限で
3/3未終端だった。6bitは12,288上限の診断1回だけ9,205 token・268.377秒で正解したが、
Ollama Q4_K_Mの3回合格59.413〜91.418秒より大幅に冗長である。64GB不足ではないが
通常ゲートの終端・速度を満たさないため、`NOVEL_DB_*`へ配線せず比較用に限定する。
評価後はserverを停止し、Qwen / bge-m3のhealth、短答、1,024次元embeddingを再確認する。

NVIDIA公式例はthinkingを`chat_template_kwargs.enable_thinking=true`で明示し、
`temperature=1.0 / top_p=0.95 / max_tokens=16000`を使う。Ollamaでは対応するnative requestを
`think=true`とし、thinkingは`message.thinking`、最終本文は`message.content`として別々に保存する。
ただし30B Q4_K_Mの汎用事実抽出は、8〜27ページだけでなく24〜27ページへ縮めても
16,000 output tokenを使い切って最終形式へ到達しなかった。比較運用ではthinkingをserver既定にせず、
directの短block抽出と型付き局所照合を先に使う。thinkingは、正解固定fixtureでdirect不合格かつ
短い根拠窓へ限定できる判定だけrequest単位で有効にする。

### 5.4 Ornith 1.5 35B-A3B（比較用・GPU smoke合格）

Ornith 1.5 35B-A3BはQwen3.5系のMoEで、約35B total / 約3B active、最大262,144 token、
Thinkingとtool callingを備える。M1 Max 64GBでは公式MLX 4bit版をstock
`mlx-lm 0.31.3 / mlx 0.32.0`で評価する。repo外へ固定revisionで取得し、
`--trust-remote-code`は使用しない。

```bash
/path/to/pic2pdf-mlx/.venv/bin/hf download \
  ornith-ai/Ornith-1.5-35B-A3B-MLX-4bit \
  --revision 19504d912fa8fc7622bf6b1de3db5d5d890b1f02 \
  --local-dir /path/to/pic2pdf-mlx/models/ornith-1.5-35b-a3b-4bit
```

固定配布物は14件、19,530,936,278 bytes（18.2GiB）である。4 shard、tokenizer、
画像のSHA-256、通常Git object、safetensors header 1,757 tensorとindexを照合してからロードする。

初期設定は次のとおりとする。

| 項目 | 値 | 根拠 |
|---|---|---|
| Thinking | `enable_thinking=true` | 公式ではreasoning modelかつ既定有効。非公式の小規模評価でも無効時の算術低下が報告される |
| 通常sampling | `temperature=0.6 / top_p=0.95 / top_k=20` | 公式モデルカードの通常タスク推奨値。benchmark再現だけ`temperature=1.0` |
| 同時実行 | decode / promptとも1 | 64GBの安全余裕確保と単一利用を前提にする |
| prefix cache | size / bytesとも0 | Qwen3.5 hybridのprefix cache再利用不整合を避ける |
| prefill step | 2,048 | MLX-LM既定。実測を取る前に独自調整しない |
| KV / activation量子化 | 初期試験では無効 | 20GB前後で収まり、まず品質差を混入させない |
| bind | `127.0.0.1`のみ | `mlx_lm.server`は基本的なsecurity checkだけのため外部公開しない |

比較用port `11440`へ次のように単独起動する。Qwen / bge-m3の採用serverを変更せず、
評価終了後は`Ctrl+C`で停止する。

```bash
/path/to/pic2pdf-mlx/.venv/bin/mlx_lm.server \
  --host 127.0.0.1 \
  --port 11440 \
  --model /path/to/pic2pdf-mlx/models/ornith-1.5-35b-a3b-4bit \
  --temp 0.6 \
  --top-p 0.95 \
  --top-k 20 \
  --max-tokens 512 \
  --chat-template-args '{"enable_thinking":true}' \
  --decode-concurrency 1 \
  --prompt-concurrency 1 \
  --prefill-step-size 2048 \
  --prompt-cache-size 0 \
  --prompt-cache-bytes 0 \
  --log-level INFO
```

requestごとにThinkingを指定する場合はトップレベルではなく
`"chat_template_kwargs":{"enable_thinking":true}`を使う。OpenAI互換応答では
思考が`message.reasoning`、最終本文が`message.content`へ分かれる。

2026-08-21のM1 Max 64GB実測:

| 試験 | 結果 |
|---|---|
| 日本語短答、101 prompt / 145 output token | 正答・`stop`、prefill 32.287 token/s、decode 50.911 token/s、peak 19.777GB |
| `mlx_lm.benchmark`、512 prompt / 128 output、3回 | prefill平均304.922 token/s、decode平均51.780 token/s、peak 20.176GB |
| OpenAI API、`max_tokens=256` | Thinking後の最終文途中で`length`。短答でも不足 |
| OpenAI API、`max_tokens=512` | 289 completion tokenで`stop`、正答、reasoning分離成功 |
| 既存SSE正規化 | 173 completion token、usage付き`stop`で完走 |

全試験でsystem-wide swapは1,358.25MiBから増えず、server停止後の空きメモリ指標は95%へ戻った。
64GBへの技術的適合は合格とする。ただし「最終回答を1行だけ」に説明を追加する形式違反があり、
小説RAGの固定ケース・JSON Schema・長文品質は未評価である。

現行`MlxBackend`は`mlx_vlm.server`向けにトップレベル`enable_thinking`を送るため、
`mlx_lm.server`へそのまま本番配線しない。server既定をThinking有効にしたsmokeではSSE通信できるが、
request単位のon/off契約は別途実装・回帰testが必要である。`NOVEL_DB_*`は変更せず、
Qwen / bge-m3 / Gemmaの採用構成も維持する。

#### 本番採用評価の実行順序

評価serverは上記と同じ排他条件で起動し、品質試験では`--max-tokens 8192`へ広げる。
Thinkingの3回再現はseed `20260821 / 20260822 / 20260823`、公式通常sampling、
`chat_template_kwargs.enable_thinking=true`をrequestごとに明示する。non-thinking診断と
本番fact抽出は同引数を`false`へ変え、server既定値へ依存しない。

| Gate | 入力・処理 | 合格条件 | 不合格時 |
|---|---|---|---|
| A | 10巻74〜75ページ、4-key JSON、Thinking 3回 + direct 1回 | ThinkingがJSON・enum・中核意味・日本語正規名・自然停止を3/3 | serverを停止し、第1ブロックへ進まない |
| B | 8〜27ページ、現行fact抽出 + 人物再編、non-thinking | 両marker、parser、許可page、正規名、非反復、既知誤り箇所の原文照合 | API実装・残りブロックへ進まない |
| C | raw OpenAI API + 共通SSE client | request単位のthinking on/off、usage、終端、error契約が回帰test込みで一致 | `NOVEL_DB_*`へ配線しない |
| D | 4ブロック、隔離1冊、32K→64K→131K | 全機械ゲート、重大誤り0、自然停止、memory pressure / swapの実用範囲 | 直前の採用構成を維持する |

固定入力はLinux本番DBを読み取り専用で取得し、74〜75ページのSHA-256は
`7a44d23a1bdb263c7a67bcc3efa1405f1c3eeec33e076ff12efd3644e00e0f4e`、
8〜27ページは`47f62bc67042c39dbf09d0b9213041d8a6a048c98a41a5d0e3341292f6c15007`である。
raw成果物は`~/Library/Application Support/Pic2PDFViewer/experiments/`のモデル別ディレクトリへ保存し、
reasoningと最終contentを混ぜない。評価終了後はport `11440`、関連process、memory pressureを確認し、
比較serverを残さない。

#### Gate A実測（2026-08-21）

固定条件のまま実行した結果、non-thinking診断は厳格JSON・中核意味・日本語正規名・自然停止へ
1/1で合格し、9.660秒、173 completion tokenだった。ただし手動監査では、途中の「牢へ戻る」という
意図を「仮の返事」とする軽微な過剰解釈があった。

Thinkingは3回とも32.564〜33.720秒、1,206 completion token、`finish_reason=stop`だった。
中核3判定と`仁耀` / `珀陽`はコードフェンスだけを除けば3/3で正しいが、生の最終contentが
JSONコードフェンスで囲まれ、固定した厳格JSON parserには0/3だった。後付けで正規化を許可せず
Gate Aを不合格とし、Gate B〜D、backend実装、本番配線を実行しなかった。

終了後はport `11440`と関連processがなく、system-wide swapが試験前後とも1,208.81MiBであることを
確認した。現行のQwen / bge-m3 / Gemma構成を維持する。将来コードフェンス正規化を採る場合は、
許容対象を単独JSONフェンスだけに限定したadapterと回帰testを先に定義し、別試行としてGate Aから再評価する。

#### Gate A2 / A3のruntime切替手順

旧Gate Aとは別試行として、まず`mlx_lm.server` + `MlxLmBackend`の限定adapter（A2）、次に
`mlx_vlm.server 0.6.15`のnative structured output（A3）を同じ固定入力で比較する。A2の
`format="json"`はserverへ未対応の`response_format`を送らず、client側で完了後の単独JSON object /
単独`json` fenceだけをfail closedで正規化する。A3はadapterを使わず、生contentを検査する。

A3は次のようにlocalhost・同時実行1・追加KV量子化なしで起動する。`--trust-remote-code`は付けない。

```bash
/path/to/pic2pdf-mlx/.venv/bin/python -m mlx_vlm.server \
  --host 127.0.0.1 \
  --port 11440 \
  --model /path/to/pic2pdf-mlx/models/ornith-1.5-35b-a3b-4bit \
  --max-tokens 8192 \
  --enable-thinking \
  --max-num-seqs 1 \
  --prefill-step-size 2048 \
  --log-level INFO
```

request bodyはトップレベルへ`enable_thinking=true`、sampling、seed、
`response_format={"type":"json_schema",...}`を置く。Thinkingとstructured outputの併用修正は
`mlx-vlm` PR #1299に含まれる。同時request追加時にlogits processorがずれるupstream報告があるため、
本番候補評価でも`--max-num-seqs 1`を維持する。A2 / A3の切替ごとに先行serverを停止し、port
`11440`が解放されたことを確認してから次を起動する。終了後もprocess、memory pressure、swapを確認する。

Ornith配布物は`vision_config=null`のtext-only checkpointである。`mlx-vlm 0.6.13`はこの形でも
vision towerを生成してmissing 393 parametersで停止する既知不具合 #1812があるため、A3には修正PR
#1879を含む0.6.15を使う。重みや`config.json`を変更しない。更新時はdry-runで依存差を確認し、
`mlx` / `mlx-lm`を維持する。

```bash
uv pip install --python /path/to/pic2pdf-mlx/.venv/bin/python --dry-run 'mlx-vlm==0.6.15'
uv pip install --python /path/to/pic2pdf-mlx/.venv/bin/python 'mlx-vlm==0.6.15'
```

#### Gate B実測とGate B2限定診断

A3合格後の現行8〜27ページ抽出は、書籍事実・人物別事実とも8,192 completion tokenで`length`となり、
話者誤り、空の末尾page marker、中国語混入も確認した。processは約19.05GiB、swap増加0なので、
メモリを増やす、または出力上限だけを増やす対処は行わない。Gate C / Dと本番配線は停止する。

再現用評価器はLinux本番DBをread-onlyで参照し、成果物だけをローカルへ保存する。

```bash
PYTHONPATH=common/llm:backend .venv/bin/python \
  scripts/maintenance/eval_ornith_mlx_gate_b.py \
  --output-dir "/path/to/experiments/ornith-gate-b"
```

最後の原因分離として実行するGate B2は、8〜27ページを4ページ×5窓へ固定分割し、
`mlx_vlm.server 0.6.15`のnative `json_schema`で各窓を最大12事実へ拘束する。公式sampling、Thinking、
同時実行1を使い、人物別の第二生成は行わない。これは現行Gate Bの再合格ではなく、別pipeline設計の
成立可否を調べる隔離診断である。不合格時は追加runtime、全巻試験、公開物更新へ進まない。

Gate B2実測は2/5窓だけが`stop`し、残る3窓は8,192 tokenをすべてThinkingへ使ってcontent 0字だった。
成功窓にも科挙推薦人の関係逆転、page帰属違い、不自然な日本語があり、救済不成立・日本語小説RAG不採用とする。
本番DB、公開物、索引、`NOVEL_DB_*`は変更しない。

公式0.6.15の`thinking_budget`が回答前停止だけを解消できるか確認する場合は、採否を覆さないGate B3として
同じ評価器へ4,096 tokenの予算を指定する。Ornithのchat templateは`<think>`をpre-openするため、
MLX-VLMのbudget検出条件を満たす。最大8,192 tokenの残り半分を回答用に確保し、1回だけ実行する。

```bash
PYTHONPATH=common/llm:backend .venv/bin/python \
  scripts/maintenance/eval_ornith_mlx_gate_b2.py \
  --thinking-budget 4096 \
  --output-dir "/path/to/experiments/ornith-gate-b3-budget-4096"
```

1窓でも未終端、JSON不正、coverage不足、意味誤りなら追加GPU試験を終了する。全窓合格でも、3 seed、
既存Qwen比較、全事実の手動照合を経るまで本番候補へ戻さない。

Gate B3実測では、全5窓が4,902〜5,110 completion token、約98〜101秒、`stop`となり、各12事実と
全20ページcoverageを返した。`thinking_budget=4096`は停止性の対処として有効である。一方、簡体字混入、
10ページの重要発言欠落、18ページの推薦人関係逆転、25ページの理由誤帰属、26ページの華副三司使を
`苑翔景`へ誤登録する重大誤りが残った。品質条件へ不合格のため追加試験と本番配線は行わず、
Ornith serverを正常停止した。TCP 11440と関連processは0件、終了後swapは1,176.81MiBだった。
budgetは他のThinkingモデルでも品質保証ではなく、回答用tokenを予約する
停止ガードとしてのみ扱う。

#### Gate B4: 単ページの根拠引用先行診断

Gate B3の日本語RAG不採用を変更せず、解決可能性だけを調べる場合は、固定fixtureから8、10、18、25、26、
27ページを単ページで監査する。人物台帳をpromptへ渡さず、各claimへ原文の連続引用と引用内主体を必須にし、
評価器が完全一致を検査する。公式sampling、Thinking、`thinking_budget=2048`、同時実行1を固定し、
再試行しない。実行前に他のGPU利用を停止し、server起動後に次を実行する。

```bash
PYTHONPATH=common/llm:backend .venv/bin/python \
  scripts/maintenance/eval_ornith_mlx_gate_b4.py \
  --fixture "/path/to/gate-b3-thinking-budget-4096/fixture.json" \
  --output-dir "/path/to/experiments/ornith-gate-b4-evidence-first"
```

終了後はserverを停止し、TCP 11440、関連process、memory pressure、swapを確認する。6ページすべての
構造・引用一致・固定意味条件へ合格しても、本番配線やDBを変更せず、全claim手動監査と既存Qwen比較を
別Gateとして行う。不合格なら追加試験を終了する。

Gate B4実測は6/6が`stop`、raw厳格JSONへ到達したが、12引用中の完全一致は5件、主体包含は6件、
両方を満たしたのは1件だけで0/6ページ合格だった。固定意味条件は10/14で、推薦人関係、衝突主体、
同一人物疑惑、荷物検査許可が欠落した。直接引用生成は不採用とし、追加GPU試験を終了する。
開始前後のswapは1,168.81MiBで不変、終了後memory free 96%、TCP 11440と関連processは0件だった。
将来の根拠ID方式は、まず既存Qwen / Solで評価し、Ornith serverを再起動する理由にしない。

## 6. トラブルシューティング

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
- [ADR-0019: Apple Silicon MLX](../基本設計/ADR/0019_apple-silicon-mlx-inference.md)
- [Ornith 1.5 35B-A3B公式モデルカード](https://huggingface.co/ornith-ai/Ornith-1.5-35B-A3B)
- [Ornith 1.5 35B-A3B公式MLX 4bit](https://huggingface.co/ornith-ai/Ornith-1.5-35B-A3B-MLX-4bit)
- [MLX-LM long prompt / cache公式説明](https://github.com/ml-explore/mlx-lm#long-prompts-and-generations)
- [MLX-LM HTTP server仕様](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/SERVER.md)
- [MLX-LM request単位Thinkingの報告](https://github.com/ml-explore/mlx-lm/issues/1352)
- [MLX-VLM](https://github.com/Blaizzy/mlx-vlm)
- [MLX-VLM structured output + Thinking修正](https://github.com/Blaizzy/mlx-vlm/pull/1299)
- [MLX-VLM同時structured outputのprocessorずれ報告](https://github.com/Blaizzy/mlx-vlm/issues/1574)
- [MLX-VLM text-only checkpointのvision tower誤生成](https://github.com/Blaizzy/mlx-vlm/issues/1812)
- [MLX-VLM text-only checkpoint修正](https://github.com/Blaizzy/mlx-vlm/pull/1879)
- [MLX-VLM 0.6.15 release](https://github.com/Blaizzy/mlx-vlm/releases/tag/v0.6.15)
- [非公式mlx-openai-server](https://github.com/cubist38/mlx-openai-server)
- [Qwen3.5 hybrid prefix cache課題](https://github.com/ml-explore/mlx-lm/issues/980)
- [M1 Max 64GB・Qwen3.5 MoE long contextのresource limit報告](https://github.com/ml-explore/mlx-lm/issues/1644)
- [Ornith 1.5 MLXのコミュニティ実測（M3 Ultra、参考値）](https://www.reddit.com/r/oMLX/comments/1vtg1rv/ornith_seems_to_be_better/)
- [Ornith 1.0の長文未終端報告（同系統・参考）](https://github.com/ornith-ai/Ornith-1/issues/18)
- [MLX-VLM native JSON Schema仕様](https://github.com/Blaizzy/mlx-vlm#structured-outputs)
- [Nemotron Puzzle MLX mixed 4/6-bit](https://huggingface.co/tekosML/Nemotron-Labs-3-Puzzle-75B-A9B-MLX-4bit-experts-6bit)
- [mlx-lm Puzzle対応PR](https://github.com/ml-explore/mlx-lm/pull/1535)
