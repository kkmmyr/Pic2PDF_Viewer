# Qwen3.8 — 公式・非公式設定の実生成比較

> 2026-10-05 実施・完了記録。採用判断と運用上の知見は [現行技術知見](../../log/技術知見/小説RAG_技術知見.md) を参照。

## 1. 結論

公式・非公式の一次資料を再確認し、隔離環境で6条件・22要求を実生成した。
具体名の質問では通常推論の低温条件が3 seedとも全契約を満たしたが、建物の質問へ広げると
原文引用の改行削除・地の文引用形式の省略が残った。設定変更だけで品質ゲートを通ったとは判定しない。

全22要求は回答を返して自然停止した。接続・停止の成功と、意味・原文引用・補足の正しさを分けて判定する。
本番Qwen3.6、設定、DB/索引を変更せず、Qwen3.8は比較限定を維持した。検証サーバーと生成ジョブは終了した。

## 2. 公式・非公式資料の扱い

- [公式model card](https://huggingface.co/Qwen/Qwen3.8-27B) のnon-thinking推奨値、thinking推奨値、low / mediumを実測対象とした。既定xhighは未実施。
- [利用者のsampling比較](https://github.com/adrienbrault/qwen3.8-27b-rtx5090/blob/main/bench/results/recommended-sampling-ab.md) からT0.6の候補を抽出した。元の評価はRTX5090 / vLLM / NVFP4の数学・指示追従・ツール課題であり、今回のMLX・日本語小説QAは元ベンチマークの再現ではない。
- [量子化の作者KL測定](https://github.com/avlp12/qwen38_alis_mlx/blob/main/docs/kl-tiers.md) は精度比較の動機になるが、日本語QA正答率を示さない。
- [M2 MaxのQ4/Q6/Q8比較投稿](https://www.reddit.com/r/LocalLLM/comments/1wsj8u0/qwen_38_27b_q4q6q8_vs_qwen_38_flashnext_on_a_96gb/) は少数の英語課題で、設定・revision・rawの情報が不十分。Q8が品質問題を解消する根拠にはしない。
- [MLX推論実験の作者repo](https://github.com/rachittshah/qwen38-mlx-inference-experiments) は改変Q4モデル・速度/メモリ中心の測定で、回答保存・意味採点がない。高速化の報告をQA品質改善と読み替えない。

その他の候補・資料の限界は [前回の資料調査](Qwen3.8_品質改善方法調査_2026-10-05.md) を参照。
同調査のMLX-VLM min_p説明は本記録§6で訂正する。

## 3. 固定条件と評価方法

| 項目 | 条件 |
|---|---|
| hardware | M1 Max 64GB |
| runtime | MLX 0.32.3 / MLX-LM 0.32.0 / MLX-VLM 0.7.4 / MLX-dspark 0.20.2 / Transformers 5.15.0 |
| model | 既取得Qwen3.8-27B MLX 4bit、revision `10c35caafbb80f7dc6a7a432cdd11af10a6d4818` |
| 推論 | DSpark baseline、drafterなし、port11441、直列、batch1 |
| context / cache | 131,072、KV8bit、prefix cache無効、全要求cached_tokens=0 |
| 共通sampling | top_k20、frequency0、repetition1は効果なし、min_p filter未実装で0相当 |
| 出力枠 | non-thinking4,096 / thinking8,192 token |
| seed | 101 / 202 / 303 |
| 入力 | 前回の固定4問fixtureの完全コピー。本文・prompt・SHAを固定。実行済み入力は約10.7K〜13.6K token |
| 第一段階 | 同じ具体名問題case1で全6条件×3 seed |
| 第二段階 | 第一段階で全3 seedの全契約を通過した条件だけ、残りcase2 / 7 / 8へ拡張。失敗検出後は次の安全境界で停止 |

アプリ共通adapterの生成bodyを使い、thinkingとsamplingの転送をassertした。
low / mediumのみ、生HTTPのtop-level `reasoning_effort`を追加した。共通adapter自体の転送修正は行っていない。
CPU上の実template展開、HTTP body、reasoning出力でthinking差を確認した。

採点は変更前から固定promptにある直接回答、ページ、発話者/地の文、逐語引用、未確認補足禁止を使った。
キーワード存在はtriageのみとし、主張と引用を原文へ手動照合した。独立した読み取り専用レビューも同じ判定となった。
新しい採点メモは生成開始後に保存したが、期待回答を追加したりpromptを変更したりしていない。

## 4. 第一段階 — 同じ具体名問題を3 seedで比較

| 条件 | thinking | temperature / top_p / presence | 具体名充足 | 全契約合格 | 中央応答時間 |
|---|---|---|---|---|---|
| 比較元の低温値 | false | 0.2 / 0.95 / 0 | 3/3 | **3/3** | 121.9秒 |
| 公式に近い値・presenceなし | false | 0.7 / 0.8 / 0 | 3/3 | 2/3 | 122.2秒 |
| 公式non-thinking推奨値 | false | 0.7 / 0.8 / 1.5 | 3/3 | 1/3 | 123.3秒 |
| 非公式報告由来のT0.6 | false | 0.6 / 0.95 / 0 | 3/3 | 2/3 | 121.2秒 |
| 公式thinking・low | true | 1.0 / 0.95 / 0 | 3/3 | 2/3 | 161.0秒 |
| 公式thinking・medium | true | 1.0 / 0.95 / 0 | 3/3 | 1/3 | 167.7秒 |

全18回答に具体名「栗鼠」が含まれたが、これは回答全体の事実正確性18/18を意味しない。
第一段階の全契約合格は11/18だった。不合格理由は次のとおり。

- seed101の公式に近い値・公式non-thinking・非公式T0.6が本文にない誤った読み「くりす」を追加。
- seed101のlow / mediumが本文にない中国語同義語「松鼠」を補足。mediumのseed202は誤読「きりす」を追加。
- 公式non-thinkingのseed303が「邵武がその正体を尋ねた」と未記載の行動を追加。具体名・引用・頁の一致だけではこの誤りを検出できない。

前回DFlashの同具体名問題は1/3、今回baseline低温は3/3だった。ただしfreshな並行条件比較をしておらず、
推論方式による乱数消費も異なる。DFlashが原因、またはbaselineが普遍的に改善すると断定しない。

## 5. 第二段階 — 低温baseline候補の追加検証

第一段階を全seed通過した低温条件だけを拡張した。建物の質問の失敗を確認した時点で
缶詰の質問seed101が既に実行中だったため、その1件を完了させて安全境界で停止した。

| 固定質問 | seed | 内容・頁 | 逐語引用 | 全契約 | 不合格理由 |
|---|---|---|---|---|---|
| case2・茶会の建物 | 101 | 合格 | NG | NG | 2文間の改行を削除 |
| case2・茶会の建物 | 202 | 合格 | NG | NG | 同じ引用内の改行削除 |
| case2・茶会の建物 | 303 | 合格 | 合格 | NG | 指定の地の文引用形式「本文には〜とあります」を省略。誤帰属はない |
| case7・缶詰の種類 | 101 | 合格 | 合格 | 合格 | 牛肉の大和煮、page45、九郎の発話に一致 |

追加4件は内容充足4/4、逐語引用2/4、全契約1/4。引用改変と形式違反を内容誤答として数えない。
低温候補の実行済み合計は固定3問・7要求で、内容充足7/7、逐語引用5/7、全契約4/7だった。
case7 seed202/303・case8全3 seedの計5要求は未実施。固定4問×3 seedを完走したとは扱わない。

46問・封印holdout・長文・本番API全体は実施していない。holdoutは開いていない。
8bit重み、KV量子化なし、xhigh、Ollama別engine、freshなbaseline/DFlash対照も未実施。

## 6. 固定runtimeの再確認と前回資料の訂正

[前回の資料調査 §3](Qwen3.8_品質改善方法調査_2026-10-05.md#3-この環境での設定互換性) の
MLX-VLM 0.7.4 `min_p`欄「通常samplerへ渡る」は誤り。
通常continuous-batching経路ではHTTP schemaとGenerationArgumentsは受け取るが、
`_make_sampler`から`_PositionedTargetSampler`へ渡すのはtemp / top_p / top_k / seedで、min_p filterを適用しない。
response_generatorがないfallbackの`stream_generate`経路は別で、min_pをkwargsで渡す。
全VLM経路が無視する、とは一般化しない。
[固定版の作者コード](https://github.com/Blaizzy/mlx-vlm/blob/v0.7.4/mlx_vlm/server/generation.py) で照合した。

DSpark 0.20.2はadapterとbaselineにmin_p filterがない。非公式候補のmin_p0.05は今回実測していない。
同版のDFlash/lookupでpresence/frequencyが生成関数へ渡らない制約、共通adapterがreasoning_effortを送らない制約は
前回と同じ。今回baselineはpresence/frequencyを反映し、effortは隔離要求に明示した。

## 7. 次の改善候補と採用の境界

1. 逐語引用を生成文から採用する代わりに、本文の行/範囲IDを選び、サーバー側でcanonical連続sliceから構成する方式を比較する。今回の改行削除・原文形式違反に直接対応する候補だが、範囲選択や質問充足の検証は別に必要。
2. 出典にない読み・別名・行動の追加を拒否する根拠検査を比較する。引用一致だけで回答全体が正しいとは扱わない。
3. モデル精度の切り分けが必要ならKV量子化なし、8bit重み、freshなbaseline/DFlash対照を別々に測る。非公式の速度・KLだけで日本語品質改善を保証しない。

いずれも未実装・未採用の候補。本番経路はMLXのため、Ollama更新をこの経路の直接的な品質修正とはしない。

## 8. 保存物・保全確認

実験root: `/Users/medaro/Developer/pic2pdf-sol-runs/qwen38-method-validation-20261005-v1/`

- `plan.json`・`fixtures/critical.json`: 変更していない条件と固定入力。
- `results/stage1.json`・`stage2-control.json`・各`.sse`: HTTP body、raw、回答、reasoning、終了理由、usage、時間。
- `results/semantic-review.json`・`stage2-semantic-review.json`: 主張・引用・全契約の手動判定。
- `proof/independent-review.json`: 独立レビューとの一致。`proof/rendered-templates.json`: 実template展開。
- `proof/preservation-after.json`・`manifest.json`: 設定9件と共通adapter11件の計20件、監査ソース16件、前回凍結調査本文のSHA不変。plan・fixture・runtime lock・旧評価helperの不変も確認。
- 常設port11437・PID37987・Qwen3.6を維持しhealthはhealthy。LinuxのQAトンネルhealthもhealthy、`pic2pdf-viewer`はactive。検証port11441のlistener消滅を確認し、調整先へGPU解放を連絡した。

アプリコード・本番設定・公開データは変更していない。追加ダウンロード・Ollama更新はしていない。
DB/索引は操作しておらず、全DBの新しいSHA監査を行ったという意味ではない。
