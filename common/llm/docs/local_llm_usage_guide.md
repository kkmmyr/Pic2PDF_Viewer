# qwen-local ツール使用ルール

MCP: qwen-local（Qwen3.6:35b-a3b、thinking モデル）を **複雑な分析・推論タスク** に使用する。
Gemma 4 と比べて高品質だが応答時間は長い（1 問 ~120 秒）。

公開ツール（MCP 経由）: `ask_qwen` / `analyze_code` / `analyze_long_text`
公開 CLI: `ask.py` / `ask.ps1`

---

## モデル仕様

| 項目 | 値 |
|---|---|
| モデル | `qwen3.6:35b-a3b`（thinking モデル） |
| サイズ | 35B（active params: 3B） |
| 平均応答時間 | ~120 秒 / 質問 |
| デフォルト `think` | `False`（Qwen 特有の事故回避、後述） |
| `num_predict` | 8192（thinking 消費の余裕） |
| `num_ctx` | 8192 |
| `temperature` | 0.2 |

設定値は `local_llm/_backend.py` の `BackendConfig.default_options` で定義。
モデルとエンドポイントは環境変数で上書き可能（`backend_from_env()` 経由、
`QWEN_MODEL` / `QWEN_OLLAMA_BASE_URL` / `QWEN_LLAMA_SERVER_BASE_URL` /
`QWEN_BACKEND` / `QWEN_TIMEOUT_SEC`）。

### Thinking の扱い（Qwen 流儀）

Qwen3.x は thinking モデルだが、**Gemma 4 と方針が真逆**。

- Gemma 4: `think=True` を一律付与（品質優先、Claude には response のみ返す）
- Qwen: `think=False` をデフォルト

**理由:** Qwen は thinking ブロックで `num_predict` を全消費し、`response` が空になる事故が PoC で確認されている。`num_predict` を 8192 に大きく取った今でも、長文タスクでは安全側に倒したい。

CLI で thinking を見たい場合は `--think` フラグで明示的に有効化する。MCP からは `think=False` 固定（オプション化していない）。

---

## Qwen vs Gemma の使い分け

| シーン | 第一選択 | 理由 |
|---|---|---|
| 単純な説明・翻訳・コード生成・画像解析 | **gemma-local** | 速い・コスト低 |
| 複雑な設計判断のセカンドオピニオン | **qwen-local** | 推論力が高い |
| 長文（小説・論文・契約書）の構造的読解 | **qwen-local** | 日本語長文に強い |
| コードのバグ発見・代替実装の提案 | **qwen-local** | より深い分析 |
| エラーメッセージの意味・正規表現生成 | **gemma-local** | Qwen を使うのは過剰 |
| まずどちらかで試したい | **gemma-local** → 浅ければ qwen-local | 段階的エスカレーション |

**運用ルール:**

1. デフォルトで gemma-local を試す
2. 回答が浅い・推論が甘い・長文の構造把握が必要 → qwen-local に切り替え
3. **Claude が処理する** べきもの（後述）は両方とも使わない

### Claude が処理する条件（Qwen も Gemma も使わない）

- 複数ファイルにまたがる解析・変更
- セキュリティ・認証・暗号化の判断
- アーキテクチャ・設計の確定判断（セカンドオピニオン用途は除く）
- バグの根本原因調査（複数ファイル参照を伴う）
- ツール実行（ファイル読み書き・Bash 等）を伴う作業

---

## MCP ツール別 使用条件

### `ask_qwen(prompt, system=None)`

**使う:**
- 設計判断のセカンドオピニオン
- 複雑なロジックの妥当性検証
- 長文・多視点の要約や論点抽出
- 日本語の高度な読解（小説・論文・契約書）

**使わない:**
- 単純な質問・コード生成 → `gemma-local` の `ask_gemma` / `generate_code`
- 翻訳 → `gemma-local` の `translate_text`
- 画像解析 → `gemma-local` の `analyze_image`

### `analyze_code(code, question="...")`

Gemma の `explain_code` よりも踏み込んだ分析（バグ発見・代替実装の提案・パフォーマンス考察など）に向く。

**使う:**
- 1 ファイル内のコードレビュー
- バグ・潜在的な問題箇所の指摘
- 代替実装案の提示

**使わない:**
- 単なる動作説明（Gemma の `explain_code` で十分）
- 複数ファイルにまたがる調査（Claude 自身で）
- 設計判断の確定（セカンドオピニオン用途は OK）

### `analyze_long_text(text, instruction)`

Qwen は日本語の長文読解に強く、`num_ctx=8192` まで読み込める。
小説・記事・議事録・調査資料の構造的な分析に向く。

**使う:**
- 小説の章ごとの要約
- 議事録の論点整理
- 契約書・規約の論点抽出

**使わない:**
- 短文の要約（Gemma の `ask_gemma` で十分）
- 8192 トークンを超える超長文（分割して複数回呼び出す）

---

## CLI ツール（ターミナルから使用）

### ask.py — Qwen への直接質問

```bash
# 通常質問
python ask.py "質問内容"

# ファイルをコンテキストに追加
python ask.py -f code.py "このコードをレビューして"

# thinking 過程も表示（デフォルトは非表示）
python ask.py --think "難しい論理パズル"

# 会話履歴を引き継ぐセッションモード（終了: exit / quit / 終了 / Ctrl+C）
python ask.py --session

# パイプ入力
echo "長い文章" | python ask.py "論点を整理して"

# モデル切り替え（環境変数 QWEN_MODEL でも可）
python ask.py -m qwen3.6:14b "質問"

# システムプロンプト指定
python ask.py --system "あなたは厳しいコードレビュアーです" -f code.py "レビュー"
```

### ask.ps1 — PowerShell ラッパー

`ask.py` と引数互換。PowerShell から短く呼ぶための薄いラッパー。

```powershell
.\ask.ps1 "質問"
.\ask.ps1 -f code.py "レビューして"
.\ask.ps1 --think "難しい論理パズル"
.\ask.ps1 --session
cat file.txt | .\ask.ps1 "論点を整理して"
```

### ログ

CLI / MCP どちらの呼び出しも `D:\61.tool\common\Qwen\logs\YYYY-MM-DD.log` に
プロンプト・応答プレビュー・経過時間を記録する。`source` で出所を区別:

| source | 出所 |
|---|---|
| `cli` | `ask.py` の単発実行 |
| `cli_session` | `ask.py --session` のセッション内 |
| `mcp:ask_qwen` | MCP `ask_qwen` ツール |
| `mcp:analyze_code` | MCP `analyze_code` ツール |
| `mcp:analyze_long_text` | MCP `analyze_long_text` ツール |

---

## トラブルシューティング

### `response` が空 / 途中で切れる

Qwen 3.x の最大の地雷。原因はほぼ次のいずれか:

1. `think=True` で thinking ブロックに `num_predict` を消費されている → CLI なら `--think` を外す、MCP は既に `think=False`
2. プロンプトが極端に長く、`num_ctx=8192` を超えている → 入力を分割する
3. `num_predict=8192` でも足りない長文タスク → `backend.ask(..., options={"num_predict": 16384})` で個別上書き

### Ollama が起動していない

```bash
ollama serve
```

CLI は接続失敗時に `エラー: Qwen 呼び出しに失敗しました: <理由>` を stderr に出して exit 1 する。

### 応答時間が長すぎる

1 問 ~120 秒は仕様。短い応答が必要なら **Gemma 4 を使うべき**。Qwen の利点は速度ではなく品質と推論力。

---

## 参照

- [README.md](../README.md) — 公開 API、設定、利用例
- [CLAUDE.md](../CLAUDE.md) — 共通モジュールの開発ルール
- [local_llm/](../local_llm/) — Backend 抽象 + 具象 + factory の実装
- [mcp_server.py](../mcp_server.py) — MCP サーバー実装
- [ask.py](../ask.py) — CLI 実装
- Gemma 4 側のガイド: `D:\61.tool\Gemma 4\docs\gemma_tool_usage_guide.md`
