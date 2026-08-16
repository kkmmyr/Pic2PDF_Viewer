# プロジェクト概要

ローカル Ollama / llama-server 上の LLM（主に Qwen3.x の thinking モデル）を
複数プロジェクトから呼び出すための共通ヘルパー。Pic2PDF workspaceでは
`qwen-common`依存、外部projectではeditable package依存として取り込み、
`from local_llm import BackendConfig, LlamaServerBackend, ...`の公開APIだけを参照する。

## 最初に読む

- README.md — 公開 API、設定、利用例、ファイル構成
- local_llm/__init__.py — 公開シンボル一覧
- local_llm/_backend.py — Backend(ABC) / BackendConfig / LLMError
- local_llm/_factory.py — `backend_from_env()`（env 変数を読むのはここだけ）

## 主要コマンド

このリポジトリ自体は実行可能な app ではなく「他プロジェクトから sys.path で
取り込まれるライブラリ」。動作確認は利用側プロジェクト（例: Pic2PDF_Viewer）か、
本リポジトリの pytest で行う。

```powershell
# 単体テスト
cd D:\61.tool\common\llm
uv run pytest -q

# 同期 API のスモーク（llama-server が :11435 で稼働している前提）
uv run --project common/llm python -c "from local_llm import backend_from_env; print(backend_from_env().ask('1+1の答えを数字だけで答えて'))"
```

## 非自明ルール

- Qwen3.x は thinking モデル。`stream=True` と thinking 抑制（Ollama では
  `think=False`、llama-server では `chat_template_kwargs.enable_thinking=false`）
  の **両方** が必須。各 Backend 実装で常にこの 2 つを送るようにしているので、
  ここを崩さないこと
- `num_predict` を小さくすると thinking ブロックで全消費されて `response` が
  空になる事故が起きる。`BackendConfig.default_options` のデフォルト 8192 は
  実測で確定した値
- `httpx` は **lazy import**（async 関数の中で `import httpx`）している。
  同期だけで使う側に httpx インストールを強制しないため。トップレベルで
  import しないこと
- 公開関数の引数は `prompt` だけ位置引数、それ以外は keyword-only（`*` 区切り）。
  利用側のコードを壊さないために、新しい引数は必ず keyword-only で末尾に追加する
- 内部モジュールは `_` プレフィックス（`_backend.py` / `_ollama.py` 等）。
  公開 API は `local_llm/__init__.py` の re-export のみ
- 環境変数を読むのは `_factory.backend_from_env()` の **1 箇所のみ**。
  他の場所では `BackendConfig` を引数で受け取る設計を維持する

## 作業スタイル

- 共通モジュールの破壊的変更は利用側プロジェクトを巻き込むので避ける
- 新機能を足すときは、既存 Backend クラスのインターフェース
  （`stream_ask` / `astream_ask` / `ask` / `aask`）と同じ命名・引数規約を踏襲する
- 利用側プロジェクトで動作確認した結果（モデルの相性、timeout の妥当性など）を
  README に追記する
- 新バックエンド（vLLM 等）追加時は `Backend` ABC を継承して `_xxx_backend.py`
  を新設、`__init__.py` と `_factory.py` で公開する流れ
