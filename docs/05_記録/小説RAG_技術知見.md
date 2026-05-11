# 小説 RAG 機能 — 技術知見の蓄積

実機検証・モデル選定・回避策・ベンチマークの記録。設計書（How を書く場所）/ ADR（単発判断）とは別に、運用で蓄えた「経験則」を残す。

最終更新: 2026-05-11（§9 LLM 推論バックエンド検証（llama.cpp vs Ollama, Phase 0〜4b）を追加）

関連:
- 設計: [バックエンド設計](../03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md)
- 機能候補: [機能追加候補](../01_要件定義/機能追加候補.md)
- LLM 切替の経緯: [ADR-0007](../02_基本設計/ADR/0007_llm-extraction-qwen-adoption.md)
- 共通 LLM モジュール: `D:\61.tool\common\llm`（A-0 リネーム前は `Qwen/`）

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

**性能への影響**（旧 Q4_K_M 27GB / Ollama 時代の値、参考）:
- CPU 計算と CPU↔GPU 通信が速度律速
- 実測生成速度: ~5.4 t/s（ctx=131k）/ ~13.8 t/s（ctx=8k）
- num_ctx を上げても OOM しないのは、足りない分が CPU 側に流れるため（ただし遅くなる）

**現状（2026-05-11、B-12 + B-14 + B-13 段階 C 採用後）**:

採用した高速化策:
- **B-12**: IQ4_XS 量子化（21GB）に切替で CPU offload を 61% → 49% に削減
- **B-14**: 推論エンジンを Ollama → llama-server に切替。`-ncmoe / -ctk q8_0 / -ctv q8_0 / -fa 1` の組合せで応答時間 5× 短縮（[ADR-0009](../02_基本設計/ADR/0009_llm-backend-llama-server.md)）
- **B-13 段階 C**: `-c 131072` で書籍 1 冊（最大 87k tokens）丸読みに対応、`-ncmoe 28` で VRAM 70% 使用 + 30% ヘッドルームを確保

結果として、scope=book の 1 冊丸読み（in_tok 78k）で **170 秒 / 9.8 t/s end-to-end**、短文 warm では **tg ~46 t/s** まで改善。詳細は §9.3 採用最適設定を参照。

---

## 1. ローカル LLM の制約と回避策

### 1.1 Qwen3.x thinking モデルの地雷

`qwen3.6:35b-a3b` を含む Qwen3.x 系は thinking モデル。以下の事故が起きる:

| 事故 | 症状 | 対処 |
|---|---|---|
| `response` 空返り | `done_reason='stop'` だが応答 0 字 | `stream=True` 必須 |
| `num_predict` 食い潰し | thinking ブロックで予算消化、本文 0 字 | `think=False` を必ず送る |
| 途中切断 | `done_reason='length'`、回答が中途半端 | `num_predict` を 4096 以上に |

これらは `D:\61.tool\common\llm\local_llm\` の各 Backend 実装で `_build_body()` がデフォルトで `stream=True` / `think=False` を強制している。利用側プロジェクトはこれを書かなくてよい設計。

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

### 2.2 QA の num_ctx・top_k 段階拡大（B-13 段階 A → B → C、2026-05-11 採用）

`llm.py:LLM_OPTIONS` の `num_ctx=8192` は PoC 当時の値だったが、B-5（書籍俯瞰サマリ）/ B-8（サマリ検索インデックス）追加で **scope=all の QA プロンプトが ~25k 字 / ~15k tokens** に膨らんでいた。実機ベンチマークで `prompt_eval_count` が **num_ctx 上限の 8,192 にぴったり張り付いている** ことが判明 = **入力時点で切り詰め発生**。

これを契機に段階的に context を拡大した:

| 段階 | num_ctx | top_k | max_per_book | scope=book 挙動 | llama-server `-c` / `-ncmoe` |
|---|---:|---:|---:|---|---|
| PoC | 8,192 | 16 | 2 | hybrid_search | (Ollama 時代) |
| A | 16,384 | 32 | 2 | hybrid_search | -c 18432 / -ncmoe 16 |
| B | 32,768 | 64 | 5 | hybrid_search | -c 36864 / -ncmoe 18 |
| **C（既定）** | **32,768**（scope=all/series）<br/>**131,072**（scope=book） | **64** | **5** | **全 page 読み**（`NOVEL_DB_QA_FULL_BOOK_MODE`） | **-c 131072 / -ncmoe 28** |

**段階 A の効果実測**:

| 設定 | scope=all のプロンプト | 実 prompt_eval | 状況 |
|---|---|---|---|
| 旧（num_ctx=8192）| 16,676〜16,809 chars | **8,192 tok**（切詰）| 後半が捨てられ、Qwen が全文を見ていない |
| 新（num_ctx=16384、段階 A）| 16,676〜16,809 chars | **10,833〜10,915 tok**（完全）| 全文を Qwen が受け取れる |

応答時間の変動は想定 +20〜30% に対し、実測 -3% 〜 +12% でほぼ誤差範囲。切り詰め解消なのに遅くならない理由は、prompt processing が 680 t/s と高速 + そもそも切り詰め前の 8192 tok でも処理時間は近い（無駄に処理してた）から。

**段階 B（B-14 後）**: B-14 の llama-server 切替で応答が 5× 速くなった分の余裕を使って `num_ctx=32768` / `top_k=64` / `max_per_book=5` に。同書籍に集中する質問への深さが向上。

**段階 C（品質優先で本採用）**: scope=book で `load_all_pages_of_book()` が hybrid_search を bypass し、書籍の全 page を page_no 順で LLM に投げる。実測で 11 巻 = 87k tokens の本に対し 78k tokens 入力 / 170 秒 / 9.8 t/s end-to-end。本文 9 箇所以上から具体的セリフ引用付き分析が得られる（段階 B では 16 page = 2.8k tokens / 37 秒で浅め）。ロールバックは `NOVEL_DB_QA_FULL_BOOK_MODE=false` の env で段階 B 相当の hybrid_search に戻る。

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
| scope=all QA（B-5/8/9/11/12/13A 全採用後）| **0%**（13 主張中 12 完全一致 + 1 言い換え）| 「シリーズ全体のテーマ」質問。逐語一致 92% |

**観察:** 1-shot のほうが文章は短くなる傾向（984 vs 1233 chars）が、密度・構造把握は深い。両方とも完全に本文に依拠している。

#### ベースライン比較（retrieval なしとの差分、2026-05-11）

「シリーズ全体のテーマ」質問について、retrieval なし（Claude の事前知識のみ）と RAG QA を比較:

| 観点 | retrieval なし | RAG QA |
|---|---|---|
| 粒度 | 「中世風 / 政治劇 / 王女主人公」程度の上位カテゴリ抽象論 | 3 軸（王権の脱構築 / 円卓の再生 / 思想の越境継承）× 巻横断引用 |
| 具体性 | 主要キャラ 1 人（レティーツィア）のみ | 5〜6 人 + 各巻象徴事件を実引用 |
| 検証可能性 | 「推察される」「であろう」 | 巻番号 + ページ番号 + 原文引用 |
| ハルシネーション率 | 検証されていない断定をすれば 100% 近い | 0% |
| 書ける文字数 | ~300 字（汎用テンプレ） | 2,000 字超の構造化テキスト |

→ retrieval なしでは具体的なシリーズ分析は物理的に不可能。RAG の存在価値が定量的に確認できた。

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

### 4.4 B-9 ctx の弱点パターン（2026-05-11 発見）

データ層品質チェックで、ctx 生成（gemma4:e4b）が **本文の重要な固有名詞・引用句を含まず、物語的解釈に流れる**事例を確認した。

**実例: Vol 9 p113 chunk 1**

本文に「王族は国の金で生きている。ならば王族は国のために尽くす義務がある」「幼い頃にベルナードが教えたことはソレスに深く染み」を含むが、生成された ctx は:

> "ソルヴェール国、ソレスとレティの対話場面で、ソレスが自らの人生と夢について内省し、自由な未来を選ぶ決意を固める場面。"

「ベルナード」「教え」「義務」「王族」が一切含まれない。

結果として、クエリ「ベルナードの教え 国民への義務」のベクトル検索で本来 1〜2 位に来るべき chunk が **6 位** (dist=0.6041) まで沈降する。直接引用に近いクエリ「王族は国のために尽くす義務 ベルナード」でも 9 位 (dist=0.5549)。

**同型: 表紙・タイトルページの ctx 捏造**

`char_count<300` のページ（表紙・著作権・タイトル）に対し、本文がほぼ空でも ctx 生成が呼ばれた結果、物語の本筋を捏造する事例が頻発（例: Vol 1 p1 タイトルカバーの ctx が「レティがデュークに真の騎士としての覚悟を確信させる場面」）。これらは `min_chars` フィルタで検索対象からは除外されているため実害は出ていないが、embedding 空間にノイズとして残る。

**救済される理由**

それでも前回の RAG QA で p113 引用が正しく出たのは、top_k=32（B-13 段階 A）+ Query Expansion（B-11）+ summary 検索（B-8）の多層防御で 6 位まで含めて拾えるため。最終 QA 出力は 92% 逐語一致 + 0% ハルシネーション。

**改善 TODO**（GPU 空き待ち、`pending_tasks.md` 高優先）

1. プロンプトに「ctx には本文に登場する重要な固有名詞・特徴フレーズを必ず含めてください」追記
2. `char_count<300` / body_page_margin 範囲のチャンクは ctx 生成 skip
3. 全 2,230 chunk 再生成（gemma4:e4b で ~100 分の見込み）

### 4.5 FTS5 vs Vector の単体精度（2026-05-11）

ハイブリッド検索のうち FTS5 単独は **抽象的な助詞混じりクエリで 0 ヒット** を起こす（`tokenize='trigram'` 設定 + `build_fts5_or_query` で min_len=2 トークン抽出の組み合わせが原因）:

| クエリ | FTS5 | Vector | Hybrid |
|---|---|---|---|
| ベルナードの教え 国民への義務 | **0 hits** | 5 hits | 5 hits ← Vector が救う |
| 戦争を起こさない国 王の誓い | **0 hits** | 5 hits | 5 hits ← 同上 |
| マティアス殺害事件の真相 | **0 hits** | 5 hits | 5 hits ← 同上 |
| グイード 取り替えっ子 出生 | 5 hits | 5 hits | 5 hits |
| おこぼれ姫 上等 国一番 | 5 hits | 5 hits | 5 hits |

具体名詞があれば FTS5 もちゃんと働く、抽象 + 助詞混じりだとマッチしないことがある — ハイブリッド検索の RRF で Vector 側が常にカバーするので最終結果は問題なし。Vector 側の品質改善（§4.4 の B-9 ctx 改良）が ROI 最大。

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

### 6.1 共通 LLM モジュール（`D:\61.tool\common\llm`、A-0 リネーム前は `Qwen/`）

- `local_llm/` パッケージは **自己完結**（利用側 `config.py` 等に依存しない）
- 設定は `BackendConfig` 引数渡し（A-3 以降）。CLI / MCP は `backend_from_env()`
  で環境変数（`QWEN_BACKEND` / `QWEN_OLLAMA_BASE_URL` / `QWEN_LLAMA_SERVER_BASE_URL`
  / `QWEN_MODEL` / `QWEN_TIMEOUT_SEC`）から Backend を 1 つ作る
- 利用側プロジェクトが `config.py` を持っていても衝突しない（`local_llm` 名前空間に閉じる）
- thinking モデル必須要件（`stream=True` / `think=False`、llama-server では
  `chat_template_kwargs.enable_thinking=False`）を各 Backend の `_build_body()` で強制

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
- **対処**: `local_llm` の Backend (`OllamaBackend` / `LlamaServerBackend`) の `ask` / `stream_ask` を使う。直接 Ollama / llama-server を叩かない

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

### 8.5 「重要キーフレーズを含むページが top-5 に来ない」

- **症状**: 本文に明らかに「○○の教え」「△△の誓い」が書かれているのに、ベクトル検索の top-5 に出ない
- **原因**: B-9 ctx が物語的解釈に流れ、本文の固有名詞や引用句を含まないため、ベクトル空間で query と離れる（§4.4 参照）
- **応急処置**:
  - `NOVEL_DB_QA_TOP_K` を 32 → 48 に上げる（GPU 余裕があれば）
  - Query Expansion (`NOVEL_DB_QA_EXPAND_ENABLED=true`) を有効にして複数視点で検索
  - クエリを「引用句っぽい言い回し」に近づけて手動で再検索
- **根本対処**: B-9 ctx 改良（プロンプトに固有名詞含有を指示）+ 全 chunk 再生成。`pending_tasks.md` 高優先で管理

---

## 9. LLM 推論バックエンド検証 (Phase 0〜4b, llama.cpp vs Ollama)

**Date**: 2026-05-11 / **関連**: [ADR-0009](../02_基本設計/ADR/0009_llm-backend-llama-server.md) / [機能追加候補 B-14](../01_要件定義/機能追加候補.md) / [LLM 層リファクタリング計画](../06_リファクタリング/LLM層リファクタリング計画.md)（A〜C 完了で Backend ABC 抽象化 + Ollama rollback 撤去）

### 9.1 検証の発端

r/LocalLLaMA で「RTX 3060 12GB で Qwen3.6-35B-A3B IQ4_XS を `llama.cpp -ncmoe 18 -t 9 -ctk q8_0 -ctv q8_0` 設定で **46.8 t/s** で動かした」という投稿があり、本機 (RTX 5070 12GB) での再現性とさらなる最適化余地を検証。判定基準は **現状 (Ollama, ~13 t/s) の 1.5× = 20 t/s 以上**を採用ラインに設定。

### 9.2 Phase 別検証結果

#### Phase 0: Ollama ベースライン

| ケース | 入力 tok | pp t/s (cold) | tg t/s |
|---|---:|---:|---:|
| A_short | 126 | 147 | 16.4 |
| B_mid | 1,990 | 634 | 14.0 |
| C_long | 8,377 | 671 | 13.0 |

`prompt_eval` rate ~670 t/s は §4 の B-13 検証時の「680 t/s」と整合（再現性確認）。

#### Phase 1: llama.cpp 入手

- 公式 b9101 Windows CUDA 13.1 ビルド (`llama-b9101-bin-win-cuda-13.1-x64.zip` + `cudart-llama-bin-win-cuda-13.1-x64.zip`) を `D:\61.tool\common\llama.cpp\b9101\` に隔離配置（PATH 変更なし、Ollama と完全共存）
- CUDA backend が RTX 5070 を正常認識: `Device 0: NVIDIA GeForce RTX 5070, compute capability 12.0, VMM: yes, VRAM: 12226 MiB`

#### Phase 2: llama-bench 投稿設定再現

```
-ncmoe 18 -t 9 -ctk q8_0 -ctv q8_0 -fa 1 -p 512 -n 128
```

結果: **pp512 = 766.6 t/s / tg128 = 76.8 t/s**（投稿 46.8 を 64% 超過、本機 GPU 世代差で説明可能）

#### Phase 2a: -ncmoe スイープ（最適点探索）

| ncmoe | pp512 t/s | tg128 t/s |
|---:|---:|---:|
| 14 | 166 | 21.5 ← GPU 過密で大幅低下 |
| **16** | **965** | **81.7** |
| 18 | 919 | 77.3 |
| 20 | 768 | 72.5 |
| 22 | 724 | 69.0 |

→ **本機の最適は `-ncmoe 16`**（投稿の 18 より 1 ステップ GPU 寄り）。

#### Phase 2b: depth スイープ（実運用シナリオ近似）

ncmoe=16 固定、`-d` で KV cache 既存 token 数を変動:

| depth | pp512 t/s | tg128 t/s |
|---:|---:|---:|
| 0 | 987 | 81.5 |
| 2,048 | 1,109 | 82.2 |
| 4,096 | 1,082 | 81.3 |
| 8,192 | 1,059 | 79.6 |
| **16,384** | **749** | **76.3** |

→ scope=all 想定の **depth=16k でも tg 76 t/s 維持**（KV cache q8_0 量子化の効果）。

#### Phase 4: E2E 比較（Ollama vs llama-server）

llama-server を `:11435` に起動（Ollama `:11434` と共存、`-np 1` 重要）。novel_db の PROMPT_TEMPLATE を模した 3 種類で実走。

**最初の試行で問題判明**: llama-server デフォルトの `n_parallel=4` で KV cache が 4 分割されて性能 1/3 に低下（tg 23 t/s）。`-np 1` を指定して再起動で解決。

#### Phase 4b: thinking 抑制（chat_template_kwargs）

Phase 4 で「llama-server の `/completion` 直叩きだと Qwen3.x thinking モデルが `<think>` ブロックで `num_predict` を食い潰す」事象を確認（B_mid で 256 tok を全部 thinking 消費、実回答ゼロ）。

解決策: `/v1/chat/completions` + `chat_template_kwargs: {enable_thinking: false}` + llama-server 側に `--jinja` フラグ。

最終結果（同一プロンプト・同一モデル・thinking 抑制済み）:

| ケース | Ollama tg | llama-server tg | tg 倍率 | Ollama 応答 | llama-server 応答 | 時間倍率 |
|---|---:|---:|---:|---:|---:|---:|
| A_short (~120 tok in) | 17.1 | **80.7** | **4.72×** | 3.75 s | **0.71 s** | **5.28×** |
| B_mid (~2k tok in) | 14.6 | **80.5** | **5.51×** | 21.25 s | **3.55 s** | **5.99×** |
| C_long (~8k tok in) | 13.4 | **78.0** | **5.82×** | 24.22 s | **14.03 s** | **1.73×★** |

★ C_long の時間倍率が小さいのは Ollama 側 warm-up で KV cache hit していたため。cold start 比なら llama-server 圧勝。

**応答品質**: 同等。Ollama 416 chars vs llama-server 147 chars の差は冗長性のみで論旨は一致（[backend/tmp_bench_phase4_*.json](../../backend/) 参照）。

### 9.3 採用最適設定

**B-14 採用時（2026-05-11、num_ctx=16384 想定）**:

```
-ncmoe 16 -c 18432   # VRAM 11.8 / 12.2 GiB (97%)
```

**B-13 段階 B（2026-05-11、num_ctx=32768、過去設定）**:

```
-ncmoe 18 -c 36864   # VRAM 11.7 / 12.2 GiB (95.8%)
```

**B-13 段階 C 本採用（2026-05-11、num_ctx=131072、現在の canonical 設定）**:

```
llama-server.exe ^
  -m D:\models\qwen3.6-35b-a3b-iq4_xs\Qwen_Qwen3.6-35B-A3B-IQ4_XS.gguf ^
  -ncmoe 28 -t 9 ^
  -ctk q8_0 -ctv q8_0 ^
  -fa 1 ^
  -ngl 99 ^
  -c 131072 ^
  -np 1 ^
  --jinja ^
  --port 11435 --host 127.0.0.1
```

起動 bat: `D:\61.tool\common\llama.cpp\b9101\start-qwen-server.bat`（タスクスケジューラ `llama-server-qwen` で自動起動）。

**ncmoe スイープ結果（2026-05-11、bench warm KV measure）**:

| -ncmoe | VRAM | A_short tg* | B_mid tg* | C_long tg* |
|---:|---:|---:|---:|---:|
| 32 | 56% (6.9 GB) | 21.4 | 55.0 | 59.4 |
| 30 | 63% (7.7 GB) | 42.9 | 53.3 | 54.2 |
| **28** | **70% (8.5 GB)** | **46.3** | **55.6** | **56.2** |

採用根拠: A_short（純粋な生成速度に近い、out_tok ~20）で -ncmoe 28 が **32 比 +116%** で最速。B_mid / C_long でも僅差トップ。VRAM 30% 余裕あり。-ncmoe 26 以下は将来の更なる最適化余地として残置（gemma4:e4b と同時稼働しないシナリオなら検討可）。

**書籍丸読み実測（2026-05-11、87k tokens の書籍 1 冊に深い質問、-ncmoe 28）**:
- VRAM: 8.5 / 12.2 GiB（70% 使用、ヘッドルーム 3.7 GiB）
- 生成速度: end-to-end 9.8 t/s（pp が depth=78k で支配的）
- 応答時間: 170 秒

### 9.4 検証で得られた重要な地雷リスト

1. **`-np 1` 必須**: llama-server のデフォルト `n_parallel=4` で KV cache が 4 分割され性能 1/3 に低下
2. **`-c <n>` は llama-bench にはない**: llama-server だけのオプション。llama-bench は GGUF のデフォルト ctx を使う
3. **thinking 抑制は `chat_template_kwargs` + `--jinja` の組合せが必須**: 片方欠けると thinking が出続ける
4. **`-ncmoe` の最適値は GPU と RAM 速度に依存**: 投稿 (3060) は 18、本機 (5070) は 16
5. **CUDA バージョン**: 本機 CUDA 13.1 ドライバには公式 `llama-b9101-bin-win-cuda-13.1-x64` が完全フィット。CUDA 12.x ビルドを使うとフォワード互換で動くが微妙な性能差が出る可能性

### 9.5 検証スクリプト

| ファイル | 役割 |
|---|---|
| `tmp_bench_qwen_phase0.py` | Phase 0 ベースライン取得（Ollama 経由） |
| `tmp_bench_phase4_compare.py` | Phase 4 / 4b E2E 比較（`--backend ollama` / `--backend llama` 切替） |
| `tmp_bench_phase0_result.txt` | Phase 0 ログ |
| `tmp_bench_phase2_*.txt` | Phase 2 / 2a / 2b の llama-bench ログ |
| `backend/tmp_bench_phase4_*.json` | Phase 4 / 4b の比較結果 JSON |

採用実装後、これらは `backend/scripts/bench_llm_backend.py` 等に整理して残す予定。

---

## 10. 関連ファイル

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
| `D:\61.tool\common\llm\local_llm\` | 共通 LLM クライアント（Backend ABC + 2 つの具象） |

---

## 追加ガイド

新しい知見が出てきたら、本ファイルに追記する。古い記述は「（旧）」と注記して残し、消さない（後から経緯を追えるように）。
