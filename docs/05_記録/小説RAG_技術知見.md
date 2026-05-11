# 小説 RAG 機能 — 技術知見の蓄積

実機検証・モデル選定・回避策・ベンチマークの記録。設計書（How を書く場所）/ ADR（単発判断）とは別に、運用で蓄えた「経験則」を残す。

最終更新: 2026-05-11

関連:
- 設計: [バックエンド設計](../03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md)
- 機能候補: [機能追加候補](../01_要件定義/機能追加候補.md)
- LLM 切替の経緯: [ADR-0007](../02_基本設計/ADR/0007_llm-extraction-qwen-adoption.md)
- 共通 LLM モジュール: `D:\61.tool\common\Qwen`

---

## 0. ハードウェア前提（重要、再発防止用）

実機は次のスペック。**VRAM を 22GB と誤記していた箇所が複数あったため、2026-05-11 に全面訂正**:

| 項目 | スペック |
|---|---|
| GPU | RTX 5070、**VRAM 12GB（dedicated）** |
| 共有 GPU メモリ（Windows 表示）| 15.6GB | システム RAM の一部、PCIe 経由で低帯域。LLM 推論ではほぼ使えない |
| システム RAM | 32GB |

**重要な事実**:
- `qwen3.6:35b-a3b`（Q4_K_M デフォルト）は **27GB** あり、12GB VRAM に乗り切らない
- Ollama は自動で **61% を CPU 側にオフロード**（システム RAM 使用）
- `ollama ps` で確認できる: `PROCESSOR    61%/39% CPU/GPU`
- 「共有 GPU メモリ 15.6GB」は Windows の仕組み上の表示。Ollama を含む LLM 推論エンジンは速度的に使わない（PCIe 帯域 ~30GB/s vs 専用 VRAM ~700GB/s で 1/20）。CPU offload 部分は通常のシステム RAM + CPU 演算

**性能への影響**:
- CPU 計算と CPU↔GPU 通信が速度律速
- 実測生成速度: ~5.4 t/s（ctx=131k）/ ~13.8 t/s（ctx=8k）
- num_ctx を上げても OOM しないのは、足りない分が CPU 側に流れるため（ただし遅くなる）

**高速化したい場合の方針**:
- より小さい量子化（IQ4_XS = ~22GB、Q3 = ~20GB）で CPU offload 比を減らす
- MTP 変種で 1 forward あたりの生成トークン数を増やす
- 詳細は機能追加候補 B-12

---

## 1. ローカル LLM の制約と回避策

### 1.1 Qwen3.x thinking モデルの地雷

`qwen3.6:35b-a3b` を含む Qwen3.x 系は thinking モデル。以下の事故が起きる:

| 事故 | 症状 | 対処 |
|---|---|---|
| `response` 空返り | `done_reason='stop'` だが応答 0 字 | `stream=True` 必須 |
| `num_predict` 食い潰し | thinking ブロックで予算消化、本文 0 字 | `think=False` を必ず送る |
| 途中切断 | `done_reason='length'`、回答が中途半端 | `num_predict` を 4096 以上に |

これらは `D:\61.tool\common\Qwen\lib\qwen_client.py` で `_build_body()` がデフォルトで `stream=True` / `think=False` を強制している。利用側プロジェクトはこれを書かなくてよい設計。

### 1.2 num_ctx と入力サイズの実機計測（2026-05-10）

書籍 1（本文 113,357 字 ≒ ~73k tokens）を 1-shot 要約させた結果:

| num_ctx | prompt_eval | response | elapsed | 結果 |
|---|---|---|---|---|
| 8,192 | 6,497（入力 10k 字）| 1,262 chars | 91s | ✅ baseline |
| 16,384 | **16,384（切詰）** | 1,146 chars | 127s | ⚠️ 入力切詰 |
| 32,768 | **32,768（切詰）** | 1,010 chars | 171s | ⚠️ 入力切詰 |
| 65,536 | **65,536（切詰）** | 653 chars | 268s | ⚠️ ぎりぎり切詰 |
| **131,072** | **70,964（完全）** | 984 chars | 287s | ✅ 完走 |

**示唆:**
- VRAM 12GB（RTX 5070）+ システム RAM 32GB の環境で `num_ctx=131,072` まで OOM なく動作する（モデルの大部分が CPU 側に offload されるため、KV cache 拡大も主にシステム RAM を使う）
- Qwen のトークナイザは **~1.54〜1.6 chars/token**（日本語）。10,000 字 → 6,497 token、113,357 字 → 70,964 token
- 大きな num_ctx でも、入力サイズが num_ctx 以下なら不利益なし（速度は ctx に比例して伸びるが、応答品質は維持）

**結論:** 一発で全文を読ませたいときは `num_ctx=131,072` を採用する（`summarizer.py` 既定）。

### 1.3 トークン換算の経験則

| 言語 | ~ chars/token (Qwen) |
|---|---|
| 日本語（漢字・カナ混在）| 1.5〜1.6 |
| 英語 | 4〜5 |

簡易計算: 日本語 1 冊 100,000 字 ≒ 60,000〜65,000 tokens。

---

## 2. モデル選定の指針

実機で確認した「タスクと適したモデルの組合せ」。

| タスク種別 | 推奨モデル | 理由 |
|---|---|---|
| 短答型（人物名抽出 / カンマ区切り出力 / 80 字位置説明） | **gemma4:e4b** | 1 件 2〜3 秒。重量モデルは過剰 |
| 構造的要約（書籍俯瞰サマリ）| **qwen3.6-iq4xs**（IQ4_XS、2026-05-11〜）| 1500 字に因果連鎖を組み込める文章生成力 + 12GB VRAM への適合 |
| QA（RAG 質問応答）| **qwen3.6-iq4xs**（IQ4_XS、2026-05-11〜）| 同上 |
| Embedding（多言語意味検索） | **bge-m3**（1024 次元）| 日本語意味距離が `nomic-embed-text` より明確に良い |

**経験則**: 「単純な短答 = 軽量、構造分析 = 重量」。Anthropic の Contextual Retrieval blog も同様の指針（位置説明は Claude Haiku で十分と推奨）。

### 2.1 Qwen 量子化グレードの選定（B-12、2026-05-11 採用）

旧 `qwen3.6:35b-a3b`（Q4_K_M、27GB）は本機 VRAM 12GB に収まり切らず、61% を CPU 側にオフロードしていた。`bartowski/Qwen_Qwen3.6-35B-A3B-GGUF` から **IQ4_XS（21GB）** を取得・登録（`ollama create qwen3.6-iq4xs`）して切替。

**実測効果**: 書籍サマリ 287s → 229s（-20%）、QA 93s → 80s（-14%）、CPU/GPU 比 61/39 → 49/51。詳細は変更履歴 2026-05-11 エントリ参照。

**選定の経緯**:
- 当初は MTP（Multi-Token Prediction）変種で 1.5〜2x 高速化を期待
- 調査の結果、MTP は Aman Gupta の patched llama.cpp 必須 → Ollama では動作しない
- IQ4_XS のみで採用、結果として 14〜20% 速度改善（モデルが GPU により多く乗ったため）

**Modelfile**（`D:\models\qwen3.6-35b-a3b-iq4_xs\Modelfile`）:

```
FROM D:/models/qwen3.6-35b-a3b-iq4_xs/Qwen_Qwen3.6-35B-A3B-IQ4_XS.gguf
TEMPLATE {{ .Prompt }}
RENDERER qwen3.5
PARSER qwen3.5
PARAMETER min_p 0
PARAMETER presence_penalty 1.5
PARAMETER repeat_penalty 1
PARAMETER temperature 1
PARAMETER top_k 20
PARAMETER top_p 0.95
```

`RENDERER qwen3.5` / `PARSER qwen3.5` は Ollama 内部の Qwen 3.5 系プロンプト整形に必須（既存 `qwen3.6:35b-a3b` から継承）。

**ロールバック**: `NOVEL_DB_LLM_MODEL=qwen3.6:35b-a3b` を環境変数で指定。旧モデルは保険として削除しない。

### 2.2 QA の num_ctx と切り詰め問題（B-13 段階 A、2026-05-11 採用）

`llm.py:LLM_OPTIONS` の `num_ctx=8192` は PoC 当時の値だったが、B-5（書籍俯瞰サマリ）/ B-8（サマリ検索インデックス）追加で **scope=all の QA プロンプトが ~25k 字 / ~15k tokens** に膨らんでいた。実機ベンチマークで `prompt_eval_count` が **num_ctx 上限の 8,192 にぴったり張り付いている** ことが判明 = **入力時点で切り詰め発生**。

| 設定 | scope=all のプロンプト | 実 prompt_eval | 状況 |
|---|---|---|---|
| 旧（num_ctx=8192）| 16,676〜16,809 chars | **8,192 tok**（切詰）| 後半が捨てられ、Qwen が全文を見ていない |
| 新（num_ctx=16384、B-13 段階 A）| 16,676〜16,809 chars | **10,833〜10,915 tok**（完全）| 全文を Qwen が受け取れる |

**応答時間の変動**: 想定 +20〜30% に対し、実測 -3% 〜 +12% でほぼ誤差範囲。切り詰め解消なのに遅くならない理由は、prompt processing が 680 t/s と高速 + そもそも切り詰め前の 8192 tok でも処理時間は近い（無駄に処理してた）から。

**`NOVEL_DB_QA_TOP_K = 32`** も同時に採用（旧 16）。`max_per_book = 2` × 11 冊 = 上限 22 件まで実際は伸びる。

**注意**: `num_ctx=8192` 想定で動いていた頃の質問履歴（`qa_history.options_json`）と新設定後の履歴は同列に比較できない（前者は context が一部欠落している可能性）。

### 2.3 軽量モデル採用で時間がどう変わるか

| 用途 | qwen3.6:35b-a3b | gemma4:e4b | 倍率 |
|---|---|---|---|
| 1 チャンクの位置説明（B-9）| ~30 秒 | **~2.8 秒** | **10.7×** |
| 1 ページの主要登場人物抽出 | ~10 秒 | ~2〜3 秒 | 4× |
| 1 冊の俯瞰要約（1-shot）| ~5 分 | ❌ ctx 不足 | — |

**判断:** thinking モデルの精度が不要な「定型タスク」では gemma4:e4b を積極採用。RAG QA や構造的要約は Qwen 一択。

---

## 3. 品質改善のレイヤー構造

検索ヒットの S/N 改善と回答品質を、独立した層で重ねて積んでいる。

```
質問
  ↓
[Query Expansion]                  ← B-11（未着手、応答時間 +30s）
  ↓
[ハイブリッド検索]
  ├ FTS5 OR 検索（pages_fts）
  ├ ベクトル検索（chunks_vec）  ← B-9 で contextual_text を含めて再 embedding
  └ 書籍サマリベクトル検索        ← B-8（book_summaries_vec）
  ↓
[RRF 融合 + フィルタ]
  ├ min_chars（薄いページ除外）
  ├ body_page_margin（前付け・後付け除外）
  └ max_per_book（書籍偏り抑制）
  ↓
[プロンプト構築]
  ├ 書籍俯瞰サマリブロック        ← B-5 / B-8 で関連書籍を充実
  ├ 主要登場人物ヒント            ← character_extractor
  └ 引用ルール / 構造的分析要請
  ↓
[qwen3.6-iq4xs（num_ctx=16384、B-12 + B-13 段階 A、2026-05-11）]
  ↓
SSE ストリーミング応答
```

**直交関係:** どの層も独立に効くため、組合せると累乗的に改善する。

| 層 | 効くケース | 効果実測 |
|---|---|---|
| min_chars / body_page_margin | 章扉 / 目次 / あとがきが混入 | ノイズ激減 |
| max_per_book | scope=all で特定冊に偏る | 書籍均等化 |
| 主要登場人物ヒント | キャラ帰属の誤統合 | ハルシネ率 ~18% に抑制 |
| 書籍俯瞰サマリ（プロンプト）| 概括質問の浅さ | 因果連鎖を含む構造的回答に |
| サマリ検索インデックス | ページに引っかからない書籍も拾う | scope=all の recall 改善 |
| Contextual Retrieval | 検索の precision/recall | Anthropic 計測で 35〜49% 改善 |

---

## 4. ベンチマーク結果

### 4.1 各処理の所要時間（実機）

| 処理 | 単位 | 単価 | 全件（11 冊 / 2,230 chunks）|
|---|---|---|---|
| OCR テキスト抽出（PyMuPDF）| 1 冊 | < 1 分 | 数分 |
| チャンキング + bge-m3 embedding | 1 冊 | < 5 分 | < 30 分 |
| 主要登場人物抽出（gemma4:e4b）| 1 ページ | 1〜3 秒 | 30〜60 分 |
| 書籍俯瞰サマリ（qwen3.6:35b-a3b 1-shot）| 1 冊 | 4〜6 分 | 約 40 分 |
| サマリ vec embedding（bge-m3）| 1 冊 | 数秒 | 数十秒 |
| チャンクコンテキスト生成（gemma4:e4b）| 1 チャンク | 2.7〜2.8 秒 | **実測 98.6 分**（2,230 チャンク、失敗 0 件）|
| チャンク再 embedding（bge-m3 バッチ 16）| 1 冊 ~200 chunks | ~30 秒 | 数分 |

### 4.2 ハルシネーション率

書籍 1 巻のサマリ生成で実機検証:

| 方式 | ハルシネーション率 | 備考 |
|---|---|---|
| map-reduce 経路（旧、num_ctx=16384）| **0%**（10 主張を検証）| 個別シーン中心、因果連鎖は弱い |
| 1-shot 経路（新、num_ctx=131072）| **0%**（17 主張を検証）| 因果連鎖・派閥構造を捕捉、構造把握深い |

**観察:** 1-shot のほうが文章は短くなる傾向（984 vs 1233 chars）が、密度・構造把握は深い。両方とも完全に本文に依拠している。

### 4.3 retrieval 精度（B-9 パイロット後の実測）

「父王が次期女王を発表する場面」(scope=book で 1 巻) のクエリで:

```
top 1: p11   score=0.0318  ← 正解（「父親は…奇策を講じた…レティーツィアに継がせる」）
top 2: p100  score=0.0288
top 3: p 28  score=0.0276
top 4: p  8  score=0.0254
top 5: p  9  score=0.0253
```

contextual_text が「該当場面の位置説明」を embedding に含むため、抽象的なクエリでも該当ページが top に来る。

---

## 5. クラウド LLM 比較（採用しなかった分析）

DeepSeek V3.x 級のクラウド API を使う場合の試算（2026-05-10 時点）:

### コスト

| 用途 | 入力 tokens | 出力 tokens | コスト |
|---|---|---|---|
| 書籍サマリ全 11 冊 | 627k | 22k | **~¥30〜50** |
| ページ単位キャラ抽出（1,359 ページ）| 1M | 20k | **~¥50** |
| 1 QA クエリ（scope=all フル context）| 627k | 2k | **~¥30**（cache miss）/ **~¥5**（cache hit）|
| QA 月 100 回 | — | — | **~¥500〜3,000** |

→ コスト面の障壁はほぼゼロ。

### 採用しなかった理由

1. **コンテンツポリシー**: 小説の性的描写を refuse される可能性（DeepSeek は緩めだが完全ではない）
2. **プライバシー**: Kindle 購入小説の全文を中国側クラウドに送信することへの懸念
3. **要件定義 §1.3** で「ローカル完結」を前提として明文化済み（[小説テキスト検索・RAG機能.md](../01_要件定義/小説テキスト検索・RAG機能.md)）
4. **ローカル代替の成立**: B-6（num_ctx 拡大）で 1 冊フル context が動くと判明したため、「部分読み問題」の本質的解決をローカルでできるようになった

**結論:** B-7 として候補に残してはいるが、本機（VRAM 12GB + システム RAM 32GB）で CPU offload 込みでも要件は満たせている見込み。速度面での改善余地は B-12（量子化変更 / MTP 採用）で検討する。

---

## 6. 実装パターン

### 6.1 共通 Qwen モジュール（`D:\61.tool\common\Qwen`）

- `lib/qwen_client.py` は **自己完結**（`config` モジュール非依存）
- 設定は環境変数（`QWEN_OLLAMA_BASE_URL` / `QWEN_MODEL` / `QWEN_TIMEOUT_SEC`）から **呼び出しごとに** 読み直す（プロセス起動後の上書きにも追随）
- 利用側プロジェクトが `config.py` を持っていても衝突しない（`lib/` を直接 `sys.path` 追加）
- thinking モデル必須要件（`stream=True` / `think=False`）を `_build_body()` で強制

経緯: [ADR-0007](../02_基本設計/ADR/0007_llm-extraction-qwen-adoption.md)

### 6.2 スキーママイグレーション

`services/novel_db/schema.py:_migrate()` で冪等 ALTER。以下を順次追加してきた:

| 追加カラム / テーブル | 用途 | 追加日 |
|---|---|---|
| `pages.main_characters` | キャラ帰属誤統合の抑制（character_extractor 生成）| 2026-05-10 |
| `books.summary` / `books.summary_generated_at` | 書籍俯瞰サマリ（B-5 / B-6）| 2026-05-10 |
| `book_summaries_vec` (vec0) | サマリの検索インデックス（B-8）| 2026-05-10 |
| `chunks.contextual_text` / `chunks.contextual_generated_at` | Contextual Retrieval（B-9）| 2026-05-11 |

すべて NULL 許容 + テーブル欠落時の後方互換（古い DB でも検索は劣化のみで失敗しない）。

### 6.3 後方互換の原則

新しい列・テーブルが無い古い DB でも、検索 / QA は動作する。

```python
# 例: search.py:search_book_summaries
has_vec = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='book_summaries_vec'"
).fetchone()
if has_vec is None:
    return []  # 後方互換: vec テーブル欠落時は空リストを返す
```

新機能の取り込みは「再実行できる CLI を別途用意し、ユーザーが都合のいいタイミングで走らせる」スタイル。`builder.rebuild_book` には組み込まず、`build_novel_db.py` / `extract_characters.py` / `build_novel_summaries.py` / `build_chunk_contexts.py` の独立 CLI として提供。

---

## 7. ハルシネーション検証手法

LLM が生成したサマリ / 回答に対する事実確認の標準手順:

1. **具体的主張をピックアップ**: 数値 / 固有名詞 / 因果記述
2. **DB 本文を SQL で検索**: `pages.full_text LIKE '%キーワード%'`
3. **ヒット数と該当 page を確認**
4. **0 ヒット項目は疑う**:
   - 同義パラフレーズの可能性（民衆 ↔ 平民、地下埋葬室 ↔ 地下の埋葬室）→ 関連語で再検索
   - 表記揺れ（ナイツ・オブ・ラウンド ↔ ナイツオブラウンド）→ 中点・空白除いて検索
   - **本物のハルシネーション**: 該当文脈もパラフレーズもない場合のみ

**経験則:** Qwen の長文要約タスクでは 0% を実現できている。ただし複数書籍の俯瞰質問（scope=all）ではキャラ帰属誤統合が ~18% 残る（character_extractor + プロンプト改善で抑制中）。

---

## 8. トラブルシューティング

### 8.1 「Qwen の response が空」

- **症状**: `done_reason='stop'` だが応答 0 字
- **原因**: `stream=False` を使った / `think=True` で thinking ブロックに num_predict 食い潰された
- **対処**: `qwen_client.py` の `ask` / `stream_ask` を使う。直接 Ollama を叩かない

### 8.2 「VRAM OOM」

- **症状**: Ollama がエラー、process 落ち
- **対処**: `num_ctx` を一段下げる。131072 → 65536 → 32768。書籍が大きい場合は map-reduce 経路（`_ONE_SHOT_MAX_BODY_CHARS` を超えると自動切替）

### 8.3 「シリーズ全体質問の回答が浅い」

- **症状**: 「シリーズ全体のテーマは？」に対し汎用語の羅列
- **対処**: 以下を順に確認
  1. `books.summary` が生成されているか（`build_novel_summaries.py --all`）
  2. `book_summaries_vec` が更新されているか（B-8）
  3. `chunks.contextual_text` が埋まっているか（B-9）

### 8.4 「特定キャラの行動が別キャラに誤帰属」

- **症状**: 「page X で Y が～」と Z の心情なのに Y のものとして回答
- **対処**: `pages.main_characters` が埋まっているか確認（`extract_characters.py --all`）。埋まっていれば「主要登場人物: ...」ヒントがプロンプトに乗り、誤統合が抑制される

---

## 9. 関連ファイル

| パス | 役割 |
|---|---|
| `backend/services/novel_db/llm.py` | Qwen SSE 呼び出し（共通モジュール経由）|
| `backend/services/novel_db/summarizer.py` | 1-shot 書籍要約（B-5 / B-6）|
| `backend/services/novel_db/contextualizer.py` | チャンク位置説明生成（B-9）|
| `backend/services/novel_db/character_extractor.py` | 主要登場人物抽出 |
| `backend/services/novel_db/search.py` | ハイブリッド検索 + フィルタ + サマリ検索（B-8）|
| `backend/scripts/build_novel_summaries.py` | サマリ一括生成 CLI |
| `backend/scripts/extract_characters.py` | キャラ一括抽出 CLI |
| `backend/scripts/build_chunk_contexts.py` | チャンク contextualize 一括 CLI |
| `D:\61.tool\common\Qwen\lib\qwen_client.py` | 共通 Qwen クライアント |

---

## 追加ガイド

新しい知見が出てきたら、本ファイルに追記する。古い記述は「（旧）」と注記して残し、消さない（後から経緯を追えるように）。
