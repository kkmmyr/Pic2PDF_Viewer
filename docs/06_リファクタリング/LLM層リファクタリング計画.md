# LLM 層リファクタリング計画

最終更新: 2026-05-11
ステータス: **Phase A + Phase B 完了**（2026-05-11、Phase C は user 判断待ち）

## Phase B 完了サマリ

| 段階 | 内容 | 結果 |
|---|---|---|
| **B-1** | `_llm_backend.py` に `build_ollama_backend(model, *, timeout)` ヘルパー追加 | ✅ |
| **B-2** | `character_extractor.py` を `OllamaBackend.ask()` に移行（urllib 削除） | ✅ |
| **B-3** | `contextualizer.py` を同様に移行 | ✅ |
| **B-4** | `query_expander.py` を同様に移行 | ✅ |
| **B-5** | 各ファイルのテスト書き換え（`urllib.request.urlopen` mock → `_BACKEND.ask` mock） | ✅ |
| **B-6** | 設計書 §5.6 / §5.8 / §7.4 更新 | ⏭️ 不要（実装詳細ではなく振る舞い記述で抽象化済み） |

**最終検証**:
- backend: 732 件 pass（Phase A 完了時 730 件 + 2、新テスト追加分）
- ruff: 全変更ファイル clean
- 重複コード（urllib ボディ組み立て + json parse + ストリーム読み × 3 ファイル）が消滅

## Phase A 完了サマリ

| 段階 | 内容 | 結果 |
|---|---|---|
| **A-0** | ディレクトリリネーム `Qwen/` → `llm/`、`~/.claude.json` MCP パス更新 | ✅ smoke OK |
| **A-1** | 新 `local_llm/` パッケージ作成（Backend ABC + 2 つの具象 + SSE 純関数 + factory） | ✅ |
| **A-2** | `__init__.py` で公開シンボル定義 | ✅（A-1 内で実施） |
| **A-3** | Pic2PDF 移行（`_llm_backend.py` 新設、env bridge 廃止、`config` を call-time 参照に） | ✅ backend 730 件 pass |
| **A-4** | CLI / MCP を `backend_from_env()` 経由に移行 | ✅ ask.py smoke OK |
| **A-5** | 旧 `lib/qwen_client.py` / `lib/qwen_logger.py` / `config.py` / `tests/test_qwen_client.py` 削除 | ✅ |
| **A-6** | 新 `tests/test_local_llm.py` 34 件で旧 22 件を置換 | ✅ |
| **A-7** | ドキュメント更新（README / usage guide / 設計書 §7.1 / ADR 注記 / memory / 検討時ドラフト削除） | ✅ |

**最終検証**:
- common/llm: 34 件 pass
- Pic2PDF backend: 730 件 pass
- ruff: 全変更ファイル clean

## 確定事項（user 判断、2026-05-11）

| 論点 | 決定 |
|---|---|
| Q1. 旧 module-level 関数の削除タイミング | **A-5 で即削除**（後方互換 shim なし） |
| Q2. 共通モジュールのリネーム | **Phase A 内でリネーム**: `D:\61.tool\common\Qwen\` → `D:\61.tool\common\llm\`、`qwen_client.py` 廃止して `local_llm/` パッケージ化 |
| Q3. Backend の型定義 | **`abc.ABC`**（実装漏れを継承時に検出） |

ADR-0007 / ADR-0009 / B-13 / B-14 の連続検証で LLM 周りが拡張的に積み上がった結果、
責務の境界がぼやけ重複コードが目立つようになった。これを 0 ベースで設計し直し、
**「タスク × モデル × バックエンド」のマトリクスを 1 箇所で扱える構造** に整える。

関連:
- ADR-0007 / ADR-0009（採用判断は維持）
- [小説テキスト検索・RAG機能_バックエンド設計.md §7](../03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md)（採用後に §7 を再構成）
- [小説RAG_技術知見.md §9](../05_記録/小説RAG_技術知見.md)（運用知見）
- 共通モジュール: `D:\61.tool\common\Qwen\lib\qwen_client.py`

---

## 0. 全体像（A → B → C）

| Phase | 範囲 | 効果 |
|---|---|---|
| **A** | Qwen 共通モジュールの interface を env-var 依存から **明示設定オブジェクト渡し** に変更 | bridge コード消滅、テスト容易性、Gemma 共通化の足場 |
| **B** | Gemma も同じ `Backend` 抽象に乗せ、Pic2PDF の 3 ファイル分の urllib 直叩きを共通化 | character_extractor / contextualizer / query_expander の重複コード消滅 |
| **C** | Ollama 上の qwen3.6-iq4xs（rollback 残置）を撤去 | 23GB 解放、設定マトリクス縮小 |

A → B → C の順で、各 Phase 完了ごとに動作確認を挟む。本ドキュメントは **Phase A の設計確定** が目的。
B / C は §4 / §5 でスコープ予告のみ。

---

## 1. Phase A: Qwen 共通モジュールの interface 最適化

### 1.1. ゴール

- `os.environ` 経由で設定を渡す現方式を廃止し、**`BackendConfig` dataclass を引数で渡す** 形に統一
- バックエンド分岐の `if backend == "llama_server"` を **`OllamaBackend` / `LlamaServerBackend` の 2 クラス** に分離（Strategy）
- 利用側の **「`os.environ.setdefault` で bridge する」** という奇妙なパターンを排除
- Gemma が同じ `Backend` 抽象に乗れるよう、命名と signature を model 非依存に整える

### 1.2. 現状の問題点（コードで具体）

#### (a) env var 経由の暗黙設定が利用側で bridge されている

[backend/services/novel_db/llm.py:34-36](../../backend/services/novel_db/llm.py#L34-L36):
```python
os.environ.setdefault("QWEN_OLLAMA_BASE_URL", NOVEL_DB_OLLAMA_BASE_URL)
os.environ.setdefault("QWEN_BACKEND", NOVEL_DB_LLM_BACKEND)
os.environ.setdefault("QWEN_LLAMA_SERVER_BASE_URL", NOVEL_DB_LLAMA_SERVER_URL)
```
Pic2PDF の `config.py` の値を **わざわざ os.environ に書き戻して** 共通モジュールに渡している。
グローバル状態経由の設定は副作用が見えづらく、テスト時に `monkeypatch.setenv` を強要する。

#### (b) sys.path.insert の重複

[llm.py:42-44](../../backend/services/novel_db/llm.py#L42-L44) と
[summarizer.py:34-36](../../backend/services/novel_db/summarizer.py#L34-L36) と
[scripts/bench_llm_backend.py:40-42](../../backend/scripts/bench_llm_backend.py#L40-L42) で同じハードコード文字列を 3 回書いている。

#### (c) バックエンド分岐の if-elif

[lib/qwen_client.py:312-325](D:/61.tool/common/Qwen/lib/qwen_client.py) で `_backend()` の戻り値を
`stream_ask` / `astream_ask` の 2 関数 × 2 系統 = 4 箇所で if-elif している。
新バックエンド（vLLM 等）追加時に分岐を 4 箇所増やす設計。

#### (d) `_finish` 内部マーカーが見えにくい

OpenAI SSE → Ollama 形式変換のロジックが `stream_ask_llama_server` 内に展開されており、
状態管理（`pending_finish`）と HTTP 通信が同一関数に同居して読みづらい。

### 1.3. 新設計

#### 1.3.1. ファイル構成（リネーム後）

```
D:\61.tool\common\llm\               # ← 旧 D:\61.tool\common\Qwen\
├── local_llm\                       # 真のパッケージ（importable）
│   ├── __init__.py                  # 公開 API の re-export
│   ├── _backend.py                  # NEW: BackendConfig + Backend(ABC) + LLMError
│   ├── _ollama.py                   # NEW: OllamaBackend
│   ├── _llama_server.py             # NEW: LlamaServerBackend
│   ├── _sse.py                      # NEW: OpenAI SSE → Ollama dict 変換の純関数
│   ├── _factory.py                  # NEW: backend_from_env()（CLI / MCP 用）
│   └── logger.py                    # ← 旧 lib/qwen_logger.py をリネーム
├── ask.py                           # 既存（中身を新 API に移行）
├── mcp_server.py                    # 既存（中身を新 API に移行）
├── tests\                           # 既存（テスト構成を再編）
├── docs\                            # 既存（命名を local_llm に追従）
└── README.md                        # 既存（書き直し）
```

**理由**:
- `lib/` を `sys.path` に追加して `from qwen_client import ...` する旧方式は、トップレベル名 (`backend.py` 等) が他プロジェクトの import と衝突するリスクがある（特に Pic2PDF の `backend/` ディレクトリ）。
- 真のパッケージ `local_llm/` を作り、`sys.path.insert(0, r"D:\61.tool\common\llm")` の上で `from local_llm import ...` する方が衝突に強く、IDE の補完も効く。
- 内部モジュールは `_` プレフィックスで非公開を明示。公開 API は `__init__.py` の再 export だけ。

#### 1.3.2. 公開 API（新形式）

```python
# local_llm/_backend.py

@dataclass(frozen=True)
class BackendConfig:
    """LLM バックエンド 1 系統の接続設定。"""
    base_url: str
    model: str = "qwen3.6:35b-a3b"
    timeout: int = 600
    default_options: Mapping[str, Any] = field(default_factory=lambda: {
        "temperature": 0.2,
        "repeat_penalty": 1.2,
        "num_predict": 8192,
        "num_ctx": 8192,
    })


class LLMError(RuntimeError):
    """バックエンド呼び出し失敗時に投げる（旧 QwenError をリネーム）。"""


class Backend(abc.ABC):
    """生成系 API の共通 interface。同期 + async 両方を実装する。"""

    @abc.abstractmethod
    def stream_ask(self, prompt: str, *, system=None, model=None,
                   options=None, think=None, timeout=None,
                   context=None) -> Iterator[dict]: ...

    @abc.abstractmethod
    async def astream_ask(self, prompt: str, **kw) -> AsyncIterator[dict]: ...

    # ask / aask はストリーミングを集約するだけなので Backend 側に共通実装
    def ask(self, prompt: str, **kw) -> str:
        parts = []
        for ev in self.stream_ask(prompt, **kw):
            if ev.get("response"):
                parts.append(ev["response"])
            if ev.get("done"):
                break
        return "".join(parts)

    async def aask(self, prompt: str, **kw) -> str: ...  # 同上 async 版
```

```python
# local_llm/_ollama.py
class OllamaBackend(Backend):
    def __init__(self, config: BackendConfig): ...

# local_llm/_llama_server.py
class LlamaServerBackend(Backend):
    def __init__(self, config: BackendConfig): ...
    # context= が渡されたら LLMError（仕様維持）

# local_llm/_factory.py
def backend_from_env() -> Backend:
    """環境変数から Backend を 1 つ作る（CLI / MCP 専用）。
    QWEN_BACKEND / QWEN_OLLAMA_BASE_URL / QWEN_LLAMA_SERVER_BASE_URL /
    QWEN_MODEL / QWEN_TIMEOUT_SEC を読む。Pic2PDF はこれを使わず、config.py の
    値から直接 BackendConfig を作る。"""
```

```python
# local_llm/__init__.py
from local_llm._backend import Backend, BackendConfig, LLMError
from local_llm._ollama import OllamaBackend
from local_llm._llama_server import LlamaServerBackend
from local_llm._factory import backend_from_env

__all__ = [
    "Backend", "BackendConfig", "LLMError",
    "OllamaBackend", "LlamaServerBackend",
    "backend_from_env",
]
```

#### 1.3.3. 利用側の典型コード（After）

**Pic2PDF QA**（[backend/services/novel_db/llm.py](../../backend/services/novel_db/llm.py)）:
```python
from services.novel_db._llm_backend import build_qwen_backend  # 新ヘルパー

_BACKEND = build_qwen_backend()  # config.py の値から 1 度だけ作る

async def stream_qa(prompt, *, model=NOVEL_DB_LLM_MODEL,
                    options=None, timeout=600.0):
    async for event in _BACKEND.astream_ask(
        prompt, model=model, options=options or LLM_OPTIONS, timeout=timeout,
    ):
        yield event
```

```python
# backend/services/novel_db/_llm_backend.py（新規、3 ファイルで再利用）
import sys
_LLM_PKG_DIR = r"D:\61.tool\common\llm"
if _LLM_PKG_DIR not in sys.path:
    sys.path.insert(0, _LLM_PKG_DIR)

from local_llm import (
    BackendConfig, LLMError, OllamaBackend, LlamaServerBackend,
)

def build_qwen_backend() -> Backend:
    if NOVEL_DB_LLM_BACKEND == "llama_server":
        return LlamaServerBackend(BackendConfig(
            base_url=NOVEL_DB_LLAMA_SERVER_URL,
            model=NOVEL_DB_LLM_MODEL,
        ))
    if NOVEL_DB_LLM_BACKEND == "ollama":
        return OllamaBackend(BackendConfig(
            base_url=NOVEL_DB_OLLAMA_BASE_URL,
            model=NOVEL_DB_LLM_MODEL,
        ))
    raise LLMError(f"unknown NOVEL_DB_LLM_BACKEND: {NOVEL_DB_LLM_BACKEND}")
```

→ **`os.environ.setdefault` の bridge コードが消える**。`sys.path.insert` も
`_llm_backend.py` 1 箇所に集約。

**CLI / MCP**（`D:\61.tool\common\llm\ask.py` / `mcp_server.py`）:
```python
from local_llm import backend_from_env

_BACKEND = backend_from_env()  # 環境変数を読むのはここ 1 箇所のみ

# あとは _BACKEND.stream_ask(...) / _BACKEND.ask(...) を呼ぶだけ
```

`backend_from_env()` は **CLI / MCP 専用ヘルパー**として共通モジュール内に置く。
Pic2PDF はこれを使わず `build_qwen_backend()` で `config.py` の値から構築する。

### 1.4. 段階分割

| 段階 | 内容 | 後方互換 |
|---|---|---|
| **A-0** | **ディレクトリリネーム**: `D:\61.tool\common\Qwen\` → `D:\61.tool\common\llm\`。`~/.claude.json` の `qwen-local` MCP の args パスも同時更新。リネーム後に CLI `ask.py` を 1 度叩いて smoke 確認 | 旧 import path（`from qwen_client import ...`）は **A-5 まで** lib/ 内に維持される（lib/ もリネーム前の中身そのまま新パスへ移動するだけなので、`sys.path.insert` の文字列以外は変わらない） |
| **A-1** | 新パッケージ `local_llm/` を新設（`_backend.py` / `_ollama.py` / `_llama_server.py` / `_sse.py` / `_factory.py`）。既存 `lib/qwen_client.py` は **そのまま残す**（並走） | あり |
| **A-2** | `local_llm/__init__.py` で公開シンボル定義 + `local_llm/logger.py` を `lib/qwen_logger.py` から移行 | あり |
| **A-3** | Pic2PDF 側を移行（`backend/services/novel_db/_llm_backend.py` 新設、`llm.py` / `summarizer.py` / `bench_llm_backend.py` を新 API へ）。`os.environ.setdefault` 削除、`sys.path.insert` 集約 | あり |
| **A-4** | CLI (`ask.py`) / MCP (`mcp_server.py`) を `backend_from_env()` 経由に移行 | あり |
| **A-5** | 旧 `lib/qwen_client.py` / `lib/qwen_logger.py` / `lib/__init__.py` / `config.py` を **削除**。lib/ ディレクトリも削除 | **破壊** |
| **A-6** | テスト書き換え（共通モジュール `tests/` + Pic2PDF `test_novel_db_llm_backend.py`）。`monkeypatch.setenv` を `BackendConfig` のコンストラクタ引数に置き換え | — |
| **A-7** | ドキュメント更新: `README.md` / `docs/qwen_tool_usage_guide.md` を `local_llm` 命名に追従、設計書 §7.1 を新構造で書き直し、`小説RAG_LLMバックエンド切替設計案.md` 削除、memory ファイル (`reference_qwen_common.md` 等) 更新 | — |

各段階は独立 commit。A-0 は最初の地雷（global config を変える）なので、ここだけ慎重に。
A-1〜A-4 は後方互換を保つので、A-5 で問題が出ても直前 commit へ revert で復旧。

### 1.5. 影響ファイル

**ディレクトリリネーム (A-0)**:
- `D:\61.tool\common\Qwen\` → `D:\61.tool\common\llm\`

**新規 (A-1〜A-3)**:
- `D:\61.tool\common\llm\local_llm\__init__.py`
- `D:\61.tool\common\llm\local_llm\_backend.py`
- `D:\61.tool\common\llm\local_llm\_ollama.py`
- `D:\61.tool\common\llm\local_llm\_llama_server.py`
- `D:\61.tool\common\llm\local_llm\_sse.py`
- `D:\61.tool\common\llm\local_llm\_factory.py`
- `D:\61.tool\common\llm\local_llm\logger.py`（旧 `lib/qwen_logger.py` の移行先）
- `backend/services/novel_db/_llm_backend.py`（sys.path 注入 + `build_qwen_backend()`）

**変更 (A-3〜A-4, A-6, A-7)**:
- `D:\61.tool\common\llm\ask.py`（CLI: backend_from_env 経由へ）
- `D:\61.tool\common\llm\mcp_server.py`（MCP: backend_from_env 経由へ）
- `D:\61.tool\common\llm\tests\` 配下（test_qwen_client.py を分割再構成）
- `D:\61.tool\common\llm\README.md`
- `D:\61.tool\common\llm\docs\qwen_tool_usage_guide.md` → `local_llm_usage_guide.md` にリネーム
- `backend/services/novel_db/llm.py`（A-3）
- `backend/services/novel_db/summarizer.py`（A-3）
- `backend/scripts/bench_llm_backend.py`（A-3）
- `backend/tests/test_novel_db_llm_backend.py`（A-6）
- `docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md` §7.1（A-7）

**外部 config 更新 (A-0)**:
- `C:\Users\amashio\.claude.json` の `mcpServers.qwen-local.args[0]` を新パスへ
- memory ファイル `reference_qwen_common.md` / `MEMORY.md` / `pending_tasks.md` のパス記述

**削除 (A-5, A-7)**:
- `D:\61.tool\common\llm\lib\qwen_client.py`（A-5）
- `D:\61.tool\common\llm\lib\qwen_logger.py`（A-5、新場所 `local_llm/logger.py` へ移行済み）
- `D:\61.tool\common\llm\lib\__init__.py`（A-5）
- `D:\61.tool\common\llm\lib\` ディレクトリ（A-5、空になった時点）
- `D:\61.tool\common\llm\config.py`（A-5、sys.path bootstrap は不要に）
- `docs/03_詳細設計/小説RAG_LLMバックエンド切替設計案.md`（A-7、ADR-0009 にマージ）

### 1.6. テスト戦略

**共通モジュール側**（`D:\61.tool\common\Qwen\tests\`）:
- `test_backend_config.py`（新）: `BackendConfig` の dataclass 動作・default_options merge
- `test_ollama_backend.py`（新）: `OllamaBackend.stream_ask` を urllib mock で検証
- `test_llama_server_backend.py`（新）: `LlamaServerBackend.stream_ask` を urllib mock で検証（`_finish` マーカー / usage チャンク / context_resume QwenError）
- `test_sse_normalizer.py`（新）: `_convert_openai_chunk` 相当の純関数テスト
- `test_backend_from_env.py`（新）: 環境変数から正しいクラスが返ることを確認
- `test_qwen_client.py`（既存）: A-5 完了後は削除、または shim 残す場合のみ smoke test として残す

**Pic2PDF 側**:
- `test_novel_db_llm_backend.py`: `os.environ.setdefault` 経由のテストを削除し、`build_qwen_backend()` のテストに置き換え
- 既存 725 件の test pass を維持

実 LLM を叩くテストはなし（A-1〜A-7 を通じて mock で完結）。実機検証は `bench_llm_backend.py` を 1 回流すのみ。

### 1.7. リスクとロールバック

| リスク | 影響 | 対策 |
|---|---|---|
| 共通モジュールの破壊変更で CLI / MCP が動かなくなる | Claude Code から qwen-local が呼べなくなる（私の作業効率低下） | A-1〜A-4 は後方互換、A-5 のみで除去。A-5 前にスモークテスト |
| Pic2PDF QA エンドポイントが壊れる | novel タブの質問応答が落ちる | A-3 後に `bench_llm_backend.py` + 手動 1 質問で確認 |
| llama-server の SSE 解析にデグレ | `_finish` マーカー周りの状態遷移を移植ミス | `test_sse_normalizer.py` で純関数として網羅。既存テスト全 pass を pre-commit 条件に |
| 設定マトリクスの取りこぼし | `bench_llm_backend.py` の `--backend` フラグが env 経由で動いていた | A-3 で env 経由を引数経由に変更、`--backend` は `BackendConfig.base_url` 切替に置き換え |

ロールバック: 各 A-* 段階を独立した commit にする。問題が出たら該当 commit を revert。

---

## 2. リネーム (A-0) のリスク管理

A-0 はグローバル設定 (`~/.claude.json`) を変更するため、Phase A の中で最も慎重に扱う。

**手順**:
1. 現在動いている `qwen-local` MCP サーバーを停止する必要は **なし**（Claude Code が次回起動するときに新パスを読む）
2. ディレクトリリネーム実行（`Move-Item D:\61.tool\common\Qwen D:\61.tool\common\llm`）
3. `~/.claude.json` の `mcpServers.qwen-local.args[0]` を `D:\\61.tool\\common\\llm\\mcp_server.py` に書き換え
4. 新パスで CLI を 1 回叩いて smoke 確認: `python D:\61.tool\common\llm\ask.py "test"`
5. memory ファイル 3 箇所のパス記述を更新（A-7 にまとめてもよいが、ここで先に直す方が混乱が少ない）

**Windows のリネーム失敗パターン**:
- ハンドルが開いていると `Move-Item` が失敗する
- llama-server.exe は `D:\61.tool\common\llama.cpp\b9101\` 配下のため独立、影響なし
- Python プロセスが `D:\61.tool\common\Qwen\` を import 中だと失敗する → 念のため CLI / MCP のプロセスが立っていないことを Get-Process で確認

**ロールバック**: `Move-Item D:\61.tool\common\llm D:\61.tool\common\Qwen` で戻し、`~/.claude.json` を git で revert。

---

## 4. Phase B（Gemma 共通化、2026-05-11 着手）

Phase A 完了後に着手。

- 対象: [character_extractor.py](../../backend/services/novel_db/character_extractor.py) /
  [contextualizer.py](../../backend/services/novel_db/contextualizer.py) /
  [query_expander.py](../../backend/services/novel_db/query_expander.py)
  の **urllib 直叩き 3 箇所**
- 現状: 各ファイルで Ollama API ボディ組み立て + ストリーム読み + json parse がほぼコピペ

### 4.1. 実装方針

**重要な発見**: Phase A で作った `OllamaBackend` がそのまま使える。Gemma は
Ollama 経由なので、共通モジュール (`local_llm`) 側に追加実装は不要。当初検討して
いた「`D:\61.tool\common\Gemma 4\` に共通モジュール追加」は **不要**（`local_llm`
パッケージが Backend を model 非依存に提供しているため）。

`Gemma 4/lib/ollama_client.py`（既存、Pic2PDF とは別プロジェクトで利用）は
think=True 固定で別物。Pic2PDF 側 3 ファイルは `local_llm.OllamaBackend` を
think=False で使う想定なので、Gemma 4 側は触らない。

### 4.2. 段階分割

| 段階 | 内容 | 後方互換 |
|---|---|---|
| **B-1** | `_llm_backend.py` に `build_ollama_backend(model, *, timeout)` ヘルパーを追加 | あり |
| **B-2** | `character_extractor.py` を `OllamaBackend.ask()` に移行（urllib スカフォールディング削除） | あり（API 不変） |
| **B-3** | `contextualizer.py` を同様に移行 | あり |
| **B-4** | `query_expander.py` を同様に移行 | あり |
| **B-5** | 各ファイルのテスト書き換え（`urllib.request.urlopen` mock → `_BACKEND.ask` mock） | — |
| **B-6** | ドキュメント追記（設計書 §5.6 / §5.8 / §7.4）| — |

### 4.3. 設計上の決定

- 各ファイルで Backend インスタンスを module top で 1 つ持つ（`_BACKEND = build_ollama_backend(MODEL, timeout=...)`）。Backend は stateless なので 3 インスタンスでも害なし、Phase A の Pic2PDF 側パターンと統一
- 応答テキストのパース部 (`_parse_names` / `_clean_response` / `_parse_expansions`) は各ファイル固有のドメインロジックなので **各ファイルに残す**。共通化のメリットなし
- timeout は呼び出しごとに違う（character: 120s、contextualizer: 120s、query_expander: 60s）ので `BackendConfig.timeout` で個別指定
- `options`（temperature, num_predict, num_ctx 等）は呼び出し時に `backend.ask(prompt, options={...})` で渡す（PoC で確定した値を維持）

### 4.4. 影響ファイル

**変更**:
- `backend/services/novel_db/_llm_backend.py`（B-1: `build_ollama_backend` 追加）
- `backend/services/novel_db/character_extractor.py`（B-2）
- `backend/services/novel_db/contextualizer.py`（B-3）
- `backend/services/novel_db/query_expander.py`（B-4）
- `backend/tests/test_novel_db_character_extractor.py`（B-5）
- `backend/tests/test_novel_db_contextualizer.py`（B-5）
- `backend/tests/test_novel_db_query_expander.py`（B-5）
- `docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md` §5.6 / §5.8 / §7.4（B-6）

### 4.5. 完了条件

- [ ] 3 ファイルから `import json`, `import urllib.error`, `import urllib.request` が消える
- [ ] 各ファイルで `_BACKEND = build_ollama_backend(...)` が module level で 1 つ
- [ ] 既存テストが pass（mock target を `_BACKEND.ask` に置換）
- [ ] backend 全 730 件 pass を維持
- [ ] ruff clean

---

## 5. Phase C スコープ予告（Ollama 上の旧 Qwen 撤去）

Phase A / B 完了後に着手。

- `ollama rm qwen3.6-iq4xs`（23GB 解放）
- `backend/config.py` から `NOVEL_DB_LLM_BACKEND` の `ollama` 分岐コードを削除
  （`llama_server` 一択、env 切替廃止）
- ADR-0009 に「Phase C で ollama backend を撤去した」追記
- ロールバックは git revert（Ollama 上のモデルだけは `ollama pull` し直す必要があるが、IQ4_XS GGUF は `D:\models\` に残るので最悪 `ollama create` で再構築可能）

---

## 6. 完了条件

Phase A 完了の判定:

- [ ] `BackendConfig` / `OllamaBackend` / `LlamaServerBackend` / `backend_from_env` が公開されている
- [ ] `os.environ.setdefault("QWEN_*", ...)` が backend / Pic2PDF の全コードから消えている
- [ ] `sys.path.insert(0, r"D:\61.tool\common\Qwen\lib")` が Pic2PDF 側で 1 箇所に集約されている（`_llm_backend.py`）
- [ ] 共通モジュール側 + Pic2PDF 側の全テストが pass
- [ ] `bench_llm_backend.py` 実機 1 回 smoke 完走
- [ ] novel タブで実際に 1 質問して応答が返る
- [ ] 設計書 §7.1 が新構造に追従、`小説RAG_LLMバックエンド切替設計案.md` 削除済み
