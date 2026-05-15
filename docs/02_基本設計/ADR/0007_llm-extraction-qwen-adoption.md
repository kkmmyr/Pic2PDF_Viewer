# ADR-0007: 小説 RAG の質問応答 LLM を Qwen3.6 に切り替え、共通モジュールに切り出し

- **Status**: Accepted
- **Date**: 2026-05-10
- **決定者**: プロジェクトオーナー
- **関連**: [小説テキスト検索・RAG機能_バックエンド設計.md §1.2 / §2.2 / §7](../../03_詳細設計/機能別/小説テキスト検索・RAG機能_バックエンド設計.md) / `D:\61.tool\common\Qwen` / commit 履歴 2026-05-09 〜 2026-05-10
- **追補**: 2026-05-11 に [ADR-0009](0009_llm-backend-llama-server.md) で「Qwen の実行バックエンドを Ollama → llama-server に変更」を決定。モデル選定（Qwen3.6-35B-A3B IQ4_XS）の判断は本 ADR で維持されている
- **パス更新注記**: 2026-05-11 の A-0（[LLM 層リファクタリング_完了記録](../../99_アーカイブ/LLM層リファクタリング_完了記録.md)）で共通モジュールを `D:\61.tool\common\Qwen\` → `D:\61.tool\common\llm\` にリネーム、`qwen_client.py` → `local_llm/` パッケージに再構成。本 ADR 内のパス・API 名は決定時の歴史的記録としてそのまま残置

## コンテキスト

小説テキスト検索・RAG 機能を 2026-05-09 に PoC ベースで実装した（D3-1 〜 D3-4 フェーズ）。質問応答 LLM は PoC で動いていた `gemma4:26b` をそのまま採用した。

実 11 冊の DB を構築して使い始めたところ、**シリーズ全体スコープでの概括的な質問**（「テーマ」「主人公の成長」「シリーズ全体の特徴」）に対して回答が浅く、汎用的な単語の羅列で済まされる事象が頻発した。

```
「シリーズ全体のテーマは？」
→ Gemma 4:26b: 「友情・成長・冒険といった普遍的なテーマが描かれています」
   (具体的シーンの引用なし、巻ごとの対比なし、複数ページの統合なし)
```

プロンプト改善（構造的回答ルール / 具体例 3 つ以上の指示 / キャラ帰属の明示）+ 検索フィルタ追加（`min_chars` / `body_page_margin` / `max_per_book` / `top_k` 拡大）でも、Gemma の踏み込み不足は本質的に改善しなかった。**モデル自体を変更する** 必要があると判断した。

加えて、Qwen3.x 系は thinking モデル特有の地雷（`stream=True` / `think=False` を併用しないと `response` が空で返る、`num_predict` が thinking ブロックで食い潰される）があり、各プロジェクトで個別に呼び出しを書くと事故が起きやすい。

## 検討した選択肢

| 選択肢 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. Gemma 4:26b 継続 + プロンプト・検索強化のみ | プロンプト改善 + フィルタ追加で粘る | 既に試行済み。概括的な質問の踏み込み不足はモデル能力の天井。プロンプトでは突破できないことを実機で確認 |
| B. クラウド LLM（Claude / GPT-4 / Gemini）に切替 | 品質は確実に上がる | 個人 LAN ツールでクラウド送信は方針に反する（[セキュリティ設計書 §1](../../03_詳細設計/セキュリティ設計書.md)）。コストも常時稼働には不向き |
| C. GLM-5.1 / MiniMax M2.7 / Kimi K2.6 / DeepSeek V4 等の最新 OSS | クラウド級の品質をローカルで | いずれも 100B 〜 600B 級でローカル推論は VRAM 不足。本機の VRAM 24GB に収まらない |
| D. Qwen3.x 系（Qwen3.6:35b-a3b、35B 総 / 活性 3B MoE） | 35B クラスで活性 3B のため、VRAM 12GB（本機 RTX 5070）+ システム RAM の CPU offload 併用で実用速度（~5.4 t/s @ ctx=131k）で動作する | （採用） |
| E. Qwen 32B dense / Qwen3.6:27b 等の小サイズ | より軽量 | まずは品質を最優先。ダメなら下げる方針 |
| **F. D + LLM クライアントを共通モジュール化** | Qwen 採用 + thinking モデル呼び出しの再利用 | （採用） |

## 決定

1. **質問応答 LLM を `qwen3.6:35b-a3b` に切り替える**。`backend/config.py` の `NOVEL_DB_LLM_MODEL` で切替可能（環境変数 `NOVEL_DB_LLM_MODEL` で上書きできる）。
2. **主要登場人物抽出は `gemma4:e4b` を継続採用**。短答型タスクで Qwen のような重量モデルは過剰。`NOVEL_DB_CHAR_EXTRACT_MODEL` で切替可能。
3. **LLM クライアントを `D:\61.tool\common\Qwen` に切り出す**。`qwen_client.py` は自己完結（`config` モジュール非依存）にして、利用側プロジェクトとの名前衝突を回避。同期 (`ask` / `stream_ask`) と非同期 (`aask` / `astream_ask`) を提供。
4. **MCP サーバー (`mcp_server.py`) を Phase 2 として用意し、Claude Code から `qwen-local` として呼べるようにする** （`~/.mcp.json` に登録済み）。

## 根拠

### Qwen3.6:35b-a3b を選んだ理由

- 同条件（同じプロンプト、同じ context）で実測比較し、Gemma 4:26b の浅さが解消された:

  ```
  シリーズ全体スコープ「テーマ」質問:
  - Gemma 4:26b:        汎用語の羅列、具体例 0 件、830 chars (途中切断, done_reason='length')
  - Qwen3.6:35b-a3b:    具体シーン 8 件 / 巻間対比 / 章ごと分析、2246 chars (完走, done_reason='stop')
  ```

- 35B 総パラメータでも MoE で活性 3B のため、ローカル推論時間が dense 35B より大幅に短い（実測 124 秒 / Gemma 4:26b は実測 333 秒で途中切断）
- 日本語の長文読解・推論能力が高く、小説のキャラ心情・伏線・伏線回収の構造化分析に向く
- ハルシネーション率は実測 ~18%（11 件中 2 件で別キャラの行動として誤帰属）。許容範囲

### LLM クライアントを共通モジュール化した理由

- Qwen3.x 系は thinking モデル。`stream=True` / `think=False` 両方を必ず送らないと `response` が空 / 途中で切れる事故が起きる（PoC で実際に踏んだ）
- `num_predict` を小さくすると thinking ブロックで全消費されて空返答になる（経験値で 4096 〜 8192 が安全圏）
- これらの地雷を踏み抜く呼び出しを各プロジェクトで再実装したくない
- 他プロジェクト（技術検証用途、Claude Code 連携など）でも同じモデルを使いたくなる場面が増える見込み
- `D:\61.tool\Gemma 4` で確立した「`sys.path.insert` で取り込む共通モジュール」流儀が既にあり、整合させやすい

### 共通モジュールの設計判断

- `qwen_client.py` を **自己完結**（`config.py` 非依存）にした。利用側プロジェクト（例: Pic2PDF backend）が既に `config` という名前のモジュールを持っている場合に、`from config import ...` が衝突する事故を避けるため
- 設定は環境変数（`QWEN_OLLAMA_BASE_URL` / `QWEN_MODEL` / `QWEN_TIMEOUT_SEC`）から **呼び出しごとに** 読み直す。プロセス起動後の上書きにも追随できる
- Pic2PDF backend からは `lib/` を直接 sys.path 追加して `from qwen_client import astream_ask` で取り込む（パターン A）

## 結果（Consequences）

### ポジティブ

- シリーズ全体スコープの概括的な質問でも、具体シーン引用 + 巻間対比 + 構造的分析が得られるようになった（実機 11 冊で確認）
- LLM 呼び出しの thinking モデル対応コードが共通モジュールに集約され、Pic2PDF 側 `services/novel_db/llm.py` は薄いラッパに縮退した（行数 127 → 63、httpx 直接呼び出しを削除）
- Claude Code から `qwen-local` MCP サーバー経由で同じモデルを呼べるようになり、技術検証や難しい分析タスクで活用できる（Phase 2 完了済み）
- 環境変数で他モデル（`qwen3.6:27b` 等）に容易に切替可能。VRAM が逼迫したら軽量モデルへフォールバックできる

### ネガティブ・受容したコスト

- **応答時間が伸びた**: 30〜100 秒 → 80〜130 秒。UI ストリーミングで体感を緩和しているが、せっかちなユーザー体験ではなくなった。品質向上とのトレードオフとして受容
- **Pic2PDF backend が外部ディレクトリ（`D:\61.tool\common\Qwen`）に依存** するようになった。共通モジュールが破損 / 移動するとビルド不可。リスク低減のため共通モジュール側を破壊的変更しないルールを `CLAUDE.md` に明記
- **本機 VRAM は 12GB しかなく、Q4_K_M モデル（27GB）の約 61% が CPU 側にオフロードされる**（Ollama 自動配置、`ollama ps` で確認可能）。生成速度は ~5.4 t/s（ctx=131k）にとどまるが、MoE 活性 3B のため許容範囲。**当 ADR 初版で「VRAM 22GB を消費」と書いていたのは誤記**（2026-05-11 訂正）。実態はモデルサイズ ~27GB / VRAM 12GB に乗り切らない構造。改善方向は機能追加候補 B-12（量子化変更 / MTP モデル変種）を参照
- **キャラ帰属誤統合は残存**（~18%）。`main_characters` ヒントで下げたが、ゼロにはできていない

### 影響範囲

- 変更が及ぶファイル:
  - `backend/config.py` — `NOVEL_DB_LLM_MODEL` / `NOVEL_DB_CHAR_EXTRACT_MODEL` / フィルタ系定数を追加
  - `backend/services/novel_db/llm.py` — 共通 Qwen モジュール経由に書き換え
  - `backend/services/novel_db/character_extractor.py` — 新規（gemma4:e4b で主要登場人物抽出）
  - `backend/services/novel_db/search.py` — フィルタ引数 + main_characters JOIN
  - `backend/services/novel_db/builder.py` — character_extractor 呼び出し追加
  - `D:\61.tool\common\Qwen\` — 新規ディレクトリ。`qwen_client.py` / `qwen_logger.py` / `mcp_server.py` / `config.py` / `pyproject.toml`
  - `~/.mcp.json` — `qwen-local` 登録
- 後続作業:
  - 既存 DB（Gemma 4:26b 時代の構築結果）の再構築は **不要**（プロンプトと LLM の変更で、DB スキーマは変わらない）
  - `pages.main_characters` カラムが既存 DB に無い場合は再構築が必要。検索側は `IS NULL` 許容で動作する
  - Phase 3（CLI + 使い分けガイド）は別途実施

## 将来の再評価条件

- VRAM が逼迫した / より高速な軽量モデルが出た → `qwen3.6:27b` 等への切替を検討
- Qwen3.7 以降で thinking 仕様が変わった → 共通モジュールの `_build_body` を見直し
- ハルシネーション率が用途上問題になった → fine-tuning か RAG プロンプト戦略の見直し
- 個人ツールから外部公開ツールへ性質が変わった → クラウド LLM 採用も再検討
