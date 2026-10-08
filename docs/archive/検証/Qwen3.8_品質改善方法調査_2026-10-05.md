# Qwen3.8 品質改善方法の公式・利用者資料調査（2026-10-05）

> status: frozen | verified: 2026-10-05 | scope: 文献・実装の読み取り専用調査

## 結論

最優先は、生成設定が実際に反映される隔離経路での比較である。
今回の更新後QA試験は低温の思考なし設定で、公式推奨プロファイルとは異なる。
さらに固定したDSpark 0.20.2のDFlash分岐はpresence penaltyを生成関数へ渡さず、
アプリの共通adapterはreasoning_effortを送信しない。この条件では設定欄の変更だけで比較が成立しない。

次点は根拠本文の選択・配置、thinking low/medium、重み8bitとKV精度の比較。
非公式の量子化測定は8bitの検証理由になるが、日本語小説QAの具体名欠落を改善した直接証拠ではない。
調べた公式資料・作者自身の公開測定には、今回の症状を同条件で解消した事例は見つからなかった。

本調査ではGPU生成、モデル取得、Ollama更新、ソース修正、本番設定・DB/索引変更を行っていない。
以下は次回検証への提案であり、採用済み仕様ではない。

## 1. 現状と過去試験の区別

直前の[更新再検証](Qwen3.8_MLXランタイム更新再検証_2026-10-05.md)では、
MLX 4bit / DFlash2 / KV8bit、thinking=false、temperature=0.2、top_p=0.95、top_k=20、
presence/frequency=0、repeat=1、max_tokens=4096を使用した。
通常回答の具体名問題は3seedで1/3。自然停止・根拠頁一致でも「栗鼠」が抜けることを確認した。
引用方式は固定4問seed101で表示後の要点4/4だったが、1問は既存の前後canonical本文補足による回復。
モデル自身の回答充足・話者の明示・複数seed安定性とは分ける。

モデルrevisionの差はprocessor設定のみで重みは同一だった。推論環境更新による能力改善は未実証。
Ollamaは今回のQA生成経路ではなく、更新してもこのDSpark経路を直接改善しない。

過去の[小説RAG検証履歴 §9.37](小説RAG_技術検証履歴.md)には、
Ollama Q4_K_Mの要約でtemperature=0.7 / top_p=0.8を試し、長さ制御は改善しても重要事実欠落が残った記録がある。
役割表の追加後も帰属誤りが残った。これは今回のMLX短答QAとは別条件だが、samplingだけを万能策としない理由になる。

## 2. 公式資料から得られる候補

### 2.1 生成設定とthinking

公式値は次のとおり。小説QAへの適合は別途評価する。

| モード | temperature | top_p | top_k | min_p | presence_penalty | repetition_penalty |
|---|---:|---:|---:|---:|---:|---:|
| non-thinking | 0.7 | 0.8 | 20 | 0 | 1.5 | 1.0 |
| thinking | 1.0 | 0.95 | 20 | 0 | 0 | 1.0 |

公式は高いpresence penaltyで言語混在や性能低下が起こり得るとも説明している。
したがってnon-thinkingはpresence=0と1.5を分けて比較する。
長いcontextの対応能力も、短いQAの正確さの保証にはならない。
[Qwen公式モデルカード](https://huggingface.co/Qwen/Qwen3.8-27B)

reasoning_effortはlow / medium / xhigh。公式templateでは無指定時xhighで、
lowは短く考える指示、xhighは詳しく考える指示を挿入し、mediumは追加の強度指示を挿入しない。
mediumでもthinkingは有効であり、effort自体はハードなtoken予算ではない。
request bodyだけでなく、render後のtemplateと出力reasoningを確認する必要がある。
[公式chat template](https://huggingface.co/Qwen/Qwen3.8-27B/blob/main/chat_template.jinja)

### 2.2 推論方式・Ollama

DSpark作者はtargetによる検証を備えたspeculative decodingを説明している。
DFlashを外す目的は、実装差と設定転送を切り分けること。外すだけでモデル能力が上がるとは予測しない。
確率的生成では乱数消費が異なるため、同seedの通常推論とDFlashに完全同文を要求しない。
現在のREADMEの対応表より、試験に固定した版の実装を優先する。
[DSpark作者README](https://github.com/ARahim3/mlx-dspark)

Ollama 0.35.1には推論エンジン更新があるが、今回の具体名欠落を修正した記載は確認できない。
Ollamaで別エンジン比較をする場合は、modelのthinking対応値と実効設定を確認する。
現在の直接MLX経路にはOllama更新の効果が届かないため、第一候補にはしない。
[Ollama release](https://github.com/ollama/ollama/releases/tag/v0.35.1)、
[thinking仕様](https://docs.ollama.com/capabilities/thinking)

## 3. この環境での設定互換性

対象は隔離runtimeのDSpark 0.20.2 / MLX-VLM 0.7.4と、現行repositoryの共通adapter。
静的に確認した事実であり、新たな実生成による検証ではない。

| 指定項目 | adapter → DSpark | adapter → MLX-VLM |
|---|---|---|
| temperature / top_p / top_k | baseline・DFlashへ渡る | 通常samplerへ渡る |
| min_p | adapterが削除。baseline自体にもfilterがなく、無効＝0相当 | 通常samplerへ渡る |
| presence penalty | HTTPへ渡るがDFlash・lookupの生成関数には渡らない。baseline・dsparkでは反映 | 反映。既定の直近20token窓で、DSparkの生成全文カウントとは異なる |
| repeat penalty | adapterが削除する | repetition_penaltyへ変換し反映。既定窓20token |
| thinking | think引数からnested enable_thinkingへ | think引数からtop-level enable_thinkingへ |
| reasoning_effort | optionsへ加えても送信されない | optionsへ加えても送信されない |
| num_predict | max_tokensへ変換しserver上限でclamp | max_tokensへ変換 |
| num_ctx / KV精度 | bodyへ載らず起動設定で管理 | bodyへ載らず起動設定で管理 |

通常QA wrapperはthink引数を公開せずadapter既定false、引用QAは明示的にfalse。
serverの既定thinkingを変更するだけでは、現在のQAはthinking試験へ切り替わらない。
生HTTPのtop-level reasoning_effort、またはDSpark起動値を使う隔離試験経路が必要となる。
前回ランナーもsamplingとthink=falseを固定しており、未修正の再実行では候補設定を試せない。

DSparkのJSON formatは完了後の正規化であり、生成中のschema拘束ではない。
VLMは構造化出力のlogits processorを備えるが、draft併用時はjson_object・json_schemaとも拒否される。
いずれもJSONが妥当であることと、質問への意味的な充足は別である。

主な根拠箇所:

- 共通body生成: `common/llm/local_llm/_llama_server.py:116`
- MLX option変換: `common/llm/local_llm/_mlx.py:16`、DSpark削除: `_mlx_dspark.py:39`
- QA wrapper: `backend/services/novel_db/llm.py:42`、引用QA: `qa_grounding.py:138`
- 隔離DSpark: `mlx_dspark/server.py:1002`（mode別引数）、`:2069`（sampling）、`:2763`（effort）
- 隔離DSpark: `generate.py:302`（penalty）、`cli.py:377`（KV値）、`target.py:111`（cache）
- 隔離VLM: `server/generation.py:1428`（sampler）、`sample_utils.py:423`（presence窓）

隔離packageの基点は
`/Users/medaro/.local/share/pic2pdf-mlx/runtimes/qwen38-retest-20261005-v1/.venv/lib/python3.12/site-packages/`。
前回のpresenceは0なので、転送欠落だけで既存の具体名欠落を説明したことにはならない。

## 4. 非公式の一次報告と評価

ここでの「確認」は公開資料を読んだ意味であり、手元で再現した意味ではない。
公式repositoryのissueも、利用者投稿は公式の結論として扱わない。

| 資料 | 作者自身が測った内容 | 今回へ適用する際の限界 |
|---|---|---|
| [avlp12の量子化比較](https://github.com/avlp12/qwen38_alis_mlx/blob/main/docs/kl-tiers.md) | bf16基準のfull-vocab KLとtop-1一致率。raw JSON・harness公開 | 100Ktokenの英語・韓国語・コード、ctx2048。日本語QA正答率ではない |
| [adrienbraultのsampling比較](https://github.com/adrienbrault/qwen3.8-27b-rtx5090/blob/main/bench/results/recommended-sampling-ab.md) | RTX5090 / vLLM / NVFP4でT0.6対1.0。作者は指示追従の悪化を報告 | 数学・指示・tool評価。公開要約中心でcase別rawから再集計できず、non-thinking公式値の直接比較ではない |
| [chupatyの75run比較](https://github.com/chupaty/ninfer-bench) | RTX5090 / NInfer / NVFP4。5model×5profile×3coding taskのtraceと採点コード公開 | 複数設定・modelを同時変更。採点はキーワード中心で実行正解ではなく、日本語小説QAではない |
| [M4 Maxの8bit運用記録](https://suhailmohebi.com/notes/qwen-3-8-on-my-m4-max/) | M4 Max 128GBでMLX 8bitの導入・実行 | 4bit対8bitの品質比較ではない。後続の比較は別の4bit派生modelで、8bit改善の証明には使えない |
| [Qwen issue #216](https://github.com/QwenLM/Qwen3.8/issues/216) | thinking後に空回答で自然停止する症状と、effort・penaltyの利用者試験 | 冒頭の訂正版と古い本文に矛盾が残る。少数の緩和試験を確定修正としない。今回はthinking無効・非空回答 |

量子化比較でuniform4bitはKL 0.07626 / top-1一致90.54%、uniform8bitは0.00184 / 98.55%。
8bitはこのcorpusで参照出力分布に近い。具体名QAでどれだけ改善するかは不明である。
比較元モデルとこのMLX-community checkpointが全面的に同一であることも、ここでは独立検証していない。

chupatyの候補T0.65 / min_p0.05 / presence0.05 / thinking_budget1200は、探索の参考にはなる。
ただし単独の効果が分からず、採点が回答・reasoning中の単語を拾うため、「高得点」を意味精度の証拠にしない。
[公開採点コード](https://raw.githubusercontent.com/chupaty/ninfer-bench/main/bench_agentic.py)

思考を短くする派生modelとして[Swift作者card](https://huggingface.co/ukisai/Swift-Qwen3.8-27b)も確認した。
作者の表にはcodingの改善と同時にinstruction/mathの低下があり、全面的な品質維持とは読めない。
日本語QAの結果はなく、元Qwenの設定・入力・精度を比較した後の候補とする。

## 5. 根拠本文と引用方式の改善候補

根拠頁が入力済みでも答えを落としているため、検索のRecall向上だけでは今回の失敗を説明できない。
まず同じ根拠の位置・量を変えて読む能力を診断する。
関連情報の位置による成績差は[Lost in the Middle](https://arxiv.org/abs/2307.03172)、
無関係なretrieval文書の影響は[The Distracting Effect](https://aclanthology.org/2025.acl-long.892/)が示している。
どちらも今回のQwen3.8の原因を実証した論文ではなく、入力整理を試す根拠として使う。

提案する比較は、(a)正解根拠頁だけの診断用入力、(b)同じ根拠を先頭・末尾へ配置、
(c)候補集合から質問に必要な連続本文を抽出する方式。
(a)は期待頁を知る診断であり、本番の検索性能評価や実装方式として採用しない。
(c)は具体名・返答・話者・不確実性を残す抽出に限る。
[RECOMP](https://arxiv.org/abs/2310.04408)の圧縮方針は参考になるが、抽象要約で根拠を置換すると別の欠落を持ち込む。

rerankerは新規の万能策ではない。既存の[検索評価](小説RAG_技術検証履歴.md)では
Qwen3-Reranker-0.6Bが平均順位を改善しても20問中2問のR@10を悪化させ、不採用だった。
候補集合・最終回答へ渡す本文量を変更するなら、candidate Recallと個別回帰を再検証する。
単にtop_kを大幅に下げて根拠頁を候補外へ落とさない。

引用の再入力による改行欠落・地の文省略には、modelにsource_id / start_line / end_lineを選ばせ、
serverがcanonical原文から連続範囲を構成する方式が候補になる。
[Langroid作者のrelevance extractor](https://langroid.github.io/langroid/reference/agent/special/relevance_extractor_agent/)は
文番号の選択と原文再構成を実装しており、この分離の参考になる。
ID・本文revision・範囲・頁・長さを検証し、非連続な台詞を一つの引用へ連結させない。
正しく引用できても選択が不十分な可能性は残るため、具体名・話者・仮説/事実の判定を別に残す。

独立した意味検証は[Chain-of-Verification](https://arxiv.org/abs/2309.11495)を参考にできる。
ただし同一modelの誤りが相関すること、呼出と待ち時間が増えることから、第一段階にはしない。
汎用few-shotや役割分離も候補だが、既存promptは前後で規則を示しており、指示を追加すれば解決するとは扱わない。
調整用問題の具体的な期待回答をproduct promptへ挿入しない。

## 6. 推奨する比較順序（未実施）

### 6.1 設定が効く経路の比較

最初に同じ4bit / KV8bit / 入力 / 現行samplingでDFlashとtargetのみのbaselineを比較する。
baselineはdrafterなしとなり、presenceが実サンプラーへ届く。
その後baseline内で下表を比較し、engine変更とsampling変更の効果を混ぜない。

| 比較profile | thinking | temperature / top_p | presence | 目的 |
|---|---|---|---:|---|
| A | false | 0.2 / 0.95 | 0 | 更新後試験条件の対照 |
| B | false | 0.7 / 0.8 | 0 | sampling組の比較 |
| C | false | 0.7 / 0.8 | 1.5 | 公式non-thinking組の比較 |
| D / E | true・low / medium | 1.0 / 0.95 | 0 | 回答充足とreasoningコストの比較 |

top_k=20、frequency=0、cache無効、batch1、seed101/202/303を固定する。
DSpark baselineのmin_pは未実装でfilterなしの0相当。requestへ0を送信して固定したとは記録しない。
非公式候補のmin_p=0.05は、この固定版では試せない。
Bはtemperatureとtop_pを一緒に変える比較で、各項目単独の効果とはしない。
non-thinkingは出力4096を維持し、thinkingは8192/16384を候補として最終回答の余裕を検証する。
effortはtoken予算ではないため、length終了・空回答・reasoningだけの自然停止も不合格へ含める。
sampling既定値・転送body・実サンプラー引数を保存し、設定名だけで適用を認定しない。

### 6.2 入力、thinking、精度

設定比較で信号が弱い場合は根拠を短く完全に保つ入力・配置を比較する。
thinkingは現行wrapperのまま実行できないため、明示的に転送する隔離requestを用意する必要がある。

次にKV8bitと量子化なしを、同じ4bit重み・設定・入力で比較する。
DSparkは`--kv-bits 0`で通常cacheとなり、`16`は許容CLI値ではない。
Qwen hybridのrecurrent stateまで一律にKV量子化されるわけではない。
重み8bitは別の比較軸として、loaded targetを明示的に切り替える。
HTTPのmodel名だけではDSparkのtargetは切り替わらない。

[MLX-community 8bit checkpoint](https://huggingface.co/mlx-community/Qwen3.8-27B-8bit)のartifactは約29.5GB。
M1 Max 64GBで検証する候補になるが、OS・KV・一時buffer・常設Qwen3.6を含めた実測メモリ確認が必要。
同時常駐を前提にせず、既存GPU調整を踏まえた隔離時間に直列評価する。
8bitが厳しい場合は6bitも候補だが、品質結果のないまま本番へ切り替えない。

### 6.3 判定と停止条件

- 固定4問を開発用として使い、各3seedで比較。失敗seedを除外せず、生回答・reasoning・HTTP body・完了理由を保存する。
- 具体名、話者、頁、対象と主体、仮説/事実、質問への充足を原文で照合する。JSON parse、引用一致、キーワードだけで合格にしない。
- 候補を選んでから封印済み質問holdout12問へ進む。調整へ流用せず、事前に不合格条件を固定する。
- 46問のcoverage・長文・本番API全体の引用検証は、その後の別段階とする。未実施の段階を成功件数へ含めない。
- schema・引用ID方式などの実装変更は別の設計・テスト対象。本調査で現在のvalidatorや既定値は変更していない。

## 7. 調査の限界と記録

非公式測定は装置、量子化、engine、task、採点法が異なり、今回の日本語QAへそのまま一般化できない。
速度改善、出力分布の近さ、JSON構造、回答の意味品質を別々に扱った。
調査時点の公開mainやissueは今後改訂される可能性がある。
設定互換性の根拠は手元に固定したruntime版で、現在のREADME全体へ一般化しない。

本調査のsource auditと調査メタデータは
`/Users/medaro/Developer/pic2pdf-sol-runs/qwen38-improvement-research-20261005-v1/`に保存する。
現在の推奨構成・採用判断は[小説RAG技術知見](../../log/技術知見/小説RAG_技術知見.md)を参照する。
