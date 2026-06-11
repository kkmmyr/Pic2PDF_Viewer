# local_llm — 共通 LLM クライアント

ローカル Ollama / llama-server 上の LLM（主に Qwen3.x の thinking モデル）を
**複数プロジェクトから安全に呼び出す** ための共通ヘルパー。
`D:\61.tool\Gemma 4` と同じ流儀で `sys.path.insert` 経由の利用を想定する。

## なぜ共通化するのか

- Qwen3.x は thinking モデルで、`stream=True` / `think=False` の併用が必須
  （さもないと `response` が空 / 途中で切れる事故が起きる）
- 上記の地雷を踏み抜く呼び出しを各プロジェクトで再実装したくない
- バックエンド（Ollama / llama-server）の切替や、新バックエンド追加時の影響を
  1 箇所に閉じ込めたい

## 公開 API

| シンボル | 用途 |
|---|---|
| `Backend` | ABC。`stream_ask` / `astream_ask` の 2 メソッドを実装するサブクラスを定義する |
| `BackendConfig` | 接続設定の frozen dataclass（`base_url`, `model`, `timeout`, `default_options`） |
| `LLMError` | バックエンド呼び出し失敗時の例外 |
| `OllamaBackend` | Ollama `/api/generate` を NDJSON ストリーミングで叩く具象 |
| `LlamaServerBackend` | llama.cpp `llama-server` の OpenAI 互換 SSE を叩いて Ollama 形式に正規化する具象 |
| `backend_from_env` | 環境変数 (`QWEN_*`) から Backend を 1 つ作る（CLI / MCP 専用） |

`Backend` には `ask` / `aask`（ストリームを集約して完全 response を返す）の
共通実装が組み込まれているので、サブクラスは 2 つの抽象メソッドだけ書けばよい。

イベントの形式は両 backend で **Ollama 互換 dict** に統一されている
（`{"response": "...", "done": false}` / 末尾は `{"response": "", "done": true,
"done_reason": "stop", "prompt_eval_count": ..., "eval_count": ...}`）。

## 利用方法

### パターン A: アプリ側（設定を明示渡し）

`config.py` 等の値から `BackendConfig` を作って具象 Backend を instantiate。

```python
import sys
sys.path.insert(0, r"D:\61.tool\common\llm")
from local_llm import BackendConfig, LlamaServerBackend

backend = LlamaServerBackend(BackendConfig(
    base_url="http://127.0.0.1:11435",
    model="qwen3.6-iq4xs",
))

# 同期で全文取得
text = backend.ask("こんにちは、自己紹介して")

# 同期ストリーミング
for event in backend.stream_ask("長文タスク"):
    if event.get("response"):
        print(event["response"], end="", flush=True)

# async ストリーミング（FastAPI SSE 等から）
async for event in backend.astream_ask("..."):
    ...
```

利用側プロジェクトが既に `config.py` を持っていても、`local_llm` パッケージの
名前空間に閉じているので衝突しない。

### パターン B: CLI / MCP（環境変数経由）

```python
import sys
sys.path.insert(0, r"D:\61.tool\common\llm")
from local_llm import backend_from_env

backend = backend_from_env()  # QWEN_BACKEND を見て LlamaServerBackend / OllamaBackend を返す
```

## 環境変数（`backend_from_env` 専用）

| 変数 | 既定 | 用途 |
|---|---|---|
| `QWEN_BACKEND` | `llama_server` | `llama_server` / `ollama` の選択 |
| `QWEN_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama の base URL |
| `QWEN_LLAMA_SERVER_BASE_URL` | `http://127.0.0.1:11435` | llama-server の base URL |
| `QWEN_MODEL` | `qwen3.6:35b-a3b` | デフォルトモデル名 |
| `QWEN_TIMEOUT_SEC` | `600` | 1 リクエストの timeout 秒 |

`QWEN_*` プレフィックスは歴史的経緯で残っている（ADR-0007 / B-14）。
将来 Gemma 等を共通化する際に `LLM_*` への改名を検討予定。

`BackendConfig.default_options` の中身（PoC で確定した安全側パラメータ）:

| キー | 既定 |
|---|---|
| `temperature` | 0.2 |
| `repeat_penalty` | 1.2 |
| `num_predict` | 8192（thinking 消費を見越して大きめ） |
| `num_ctx` | 8192 |

`stream_ask` の `options` 引数で個別上書き可能（マージは Backend 側で行う）。

## 依存

- 同期版 (`stream_ask` / `ask`): 標準ライブラリのみ (`urllib`)
- 非同期版 (`astream_ask` / `aask`): `httpx>=0.27`（**lazy import**）

httpx は `pyproject.toml` の dependency に入っているが、同期版しか使わない
プロジェクトでは httpx をインストールしなくても動作する。

## 利用中のプロジェクト

- `D:\61.tool\Pic2PDF_Viewer\backend\services\novel_db\` — 小説 RAG の
  QA ストリーム + 書籍俯瞰サマリ生成
- `qwen-local` MCP サーバー（`mcp_server.py`、`~/.claude.json` に登録済み）
- CLI `ask.py` / `ask.ps1`

## ファイル構成

```
D:\61.tool\common\llm\
├── local_llm\                       # 公開パッケージ
│   ├── __init__.py                  # 公開シンボル re-export
│   ├── _backend.py                  # Backend(ABC) / BackendConfig / LLMError
│   ├── _ollama.py                   # OllamaBackend
│   ├── _llama_server.py             # LlamaServerBackend
│   ├── _sse.py                      # OpenAI SSE → Ollama dict 変換の純関数
│   ├── _factory.py                  # backend_from_env()
│   └── logger.py                    # mcp / cli 共通ロガー
├── ask.py                           # CLI
├── mcp_server.py                    # MCP サーバー
├── tests\                           # pytest（34 件）
├── docs\                            # 利用ガイド
└── README.md                        # 本ファイル
```

## MCP サーバー

Claude Code から Qwen3.6 をツールとして呼び出すための MCP サーバー (`mcp_server.py`)。

### 提供ツール

| ツール | 用途 |
|---|---|
| `ask_qwen(prompt, system=None)` | 汎用 Q&A。複雑な分析・推論・長文検討向き |
| `analyze_code(code, question)` | コードのレビュー・問題点指摘・代替案提示 |
| `analyze_long_text(text, instruction)` | 長文の構造的分析・要約・論点抽出（日本語に強い） |

### 提供 Resources（Pic2PDF_Viewer バックエンド起動中のみ有効）

| URI | 内容 |
|---|---|
| `novel://books` | 小説書籍一覧（タイトル・著者・シリーズ・indexed 状態・ページ数） |
| `novel://characters/{book_name}` | 指定書籍のキャラクター一覧（名前・初登場ページ・登場ページ数・サマリ有無） |

### 提供 Prompts（Pic2PDF_Viewer バックエンド起動中のみ有効）

| プロンプト名 | 引数 | 内容 |
|---|---|---|
| `novel-qa` | `book_name`（補完あり）, `question` | 書籍サマリをコンテキストに添えて質問を立てる |
| `summarize-book` | `book_name`（補完あり） | 書籍の詳細情報・サマリを整形して表示する |

`book_name` 引数は入力中に書籍一覧で補完される（MCP クライアントが補完をサポートしている場合）。

バックエンドの URL は環境変数 `NOVEL_DB_BASE_URL`（デフォルト: `http://localhost:8766`）で変更可能。
バックエンドが未起動の場合は接続エラーメッセージを返す（MCP サーバー自体はクラッシュしない）。

すべて `D:\61.tool\common\llm\logs\YYYY-MM-DD.log` にプロンプト・応答プレビュー・
経過時間を残す。

### 登録方法

`~/.claude.json` の `mcpServers` に以下を追加:

```json
{
  "mcpServers": {
    "qwen-local": {
      "command": "python",
      "args": ["D:\\61.tool\\common\\llm\\mcp_server.py"],
      "type": "stdio"
    }
  }
}
```

反映には Claude Code の再起動が必要。

### 使い分けの目安

- **gemma-local**（Gemma 4:e4b）: 単純な説明・翻訳・コード生成・画像解析。応答速度が速い
- **qwen-local**（Qwen3.6:35b-a3b）: 複雑な分析・長文検討・推論を要する質問。1 問 ~120 秒
- どちらでもよさそうなら gemma-local を先に試し、回答が浅ければ qwen-local に切り替える

## CLI

ターミナルから素早く LLM を叩くための CLI (`ask.py`)。

```powershell
# 通常質問
python ask.py "質問内容"

# ファイルをコンテキストに追加
python ask.py -f code.py "このコードをレビューして"

# thinking 過程も表示（デフォルトは非表示。Qwen は think=False が事故回避のため安全側）
python ask.py --think "難しい論理パズル"

# 会話履歴を引き継ぐセッションモード（終了: exit / quit / 終了 / Ctrl+C）
python ask.py --session

# パイプ入力
echo "長い文章" | python ask.py "論点を整理して"

# PowerShell ラッパー（引数互換）
.\ask.ps1 "質問"
```

公開オプション: `-f/--file` / `-m/--model` / `--system` / `--think` / `--session`。
詳しい使い分け・モデル仕様・トラブルシューティングは
[`docs/local_llm_usage_guide.md`](docs/local_llm_usage_guide.md) を参照。

CLI からの呼び出しも `logs/YYYY-MM-DD.log` に `cli` / `cli_session` ソースで記録される。

## Phase 履歴

- **Phase 1**（完了）: 共通ライブラリ + Pic2PDF_Viewer からの利用
- **Phase 2**（完了）: MCP サーバー化、Claude Code 連携
- **Phase 3**（完了）: CLI (`ask.py` / `ask.ps1`) と利用ガイド追加
- **B-14 / ADR-0009**（完了、2026-05-11）: llama-server バックエンド追加
  （応答 5× 高速化）
- **A-0〜A-7**（完了、2026-05-11）: Qwen 専用設計から Backend 抽象に再設計。
  ディレクトリリネーム (`Qwen/` → `llm/`)、Backend ABC + 2 つの具象 + ファクトリに
  分離、env 経由設定渡しを廃止し `BackendConfig` 引数渡しに統一。詳細は
  Pic2PDF_Viewer の `docs/06_リファクタリング/LLM層リファクタリング計画.md`
