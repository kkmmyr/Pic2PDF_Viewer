# MiMo V2.6 Distill Qwen 9B ローカルLLM評価（2026-09-23）

> status: frozen | evaluated: 2026-09-23 | hardware: Apple M1 Max / 64GB

## 結論

**MiMo-V2.6-Distill-Qwen-9B Q8_0は現行Qwen3.6の主生成・QAを置換しない。**
モデルは64GBへ余裕をもってロードでき、現行`LlamaServerBackend`のthinking制御・ストリーム・
複数ターン履歴とも接続できた。しかし、思考なしの固定ケースは2/3、追加4主張は各試行3/4、
思考ありの20ページ抽出は回答前に8,192 tokenへ達した。

- 思考なし: 固定ケース2/3。1件は理由文で逃亡継続を説明しながら、JSONの行動・statusだけ牢戻り側へ反転した。
- 思考あり: 固定ケース3/3。途中発言と最終合意を区別できた。
- 追加4主張: 3試行とも機械判定3/4。意味は概ね読めたが、根拠ページ欠落またはstatus不一致が残った。
- 20ページ抽出: 16,678入力tokenに対して8,192 completion tokenをすべてreasoningへ使い、content 0文字で終了した。
- モデルはQwen3.5-9B派生であり、独立検証モデルとしてQwen系統から十分に離れているとも扱わない。

## 評価対象と環境

| 項目 | 固定値 |
|---|---|
| 配布元 | `ggml-org/MiMo-V2.6-Distill-Qwen-9B-GGUF` |
| revision | `81baddc39bc48924a88e87b8d31aceb03058e559` |
| model | `MiMo-V2.6-Distill-Qwen-9B-Q8_0.gguf` |
| size | 9,527,498,048 bytes |
| SHA-256 | `de6dae10334e088876358ef9f574835bb3b401ea2ecf5d6a9473f37894df6b73` |
| runtime | llama.cpp `b10360-48d22e295` / Metal |
| server | `127.0.0.1:11441`、1 slot、32,768 context、`reasoning-format=deepseek` |
| sampling | 公式値 temperature 0.6 / top-p 0.95 / top-k 20 |
| 出力上限 | 8,192 token |

モデルと評価rawはrepo外へ置き、公開DB・索引・アプリ設定・通常runtimeを変更していない。
重みはHugging Face APIのsize・LFS SHAと一致することを確認した。
[公式モデルカード](https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Distill-Qwen-9B)と
[ggml-org変換](https://huggingface.co/ggml-org/MiMo-V2.6-Distill-Qwen-9B-GGUF)を参照した。

## 接続前確認

公式変換はMiMo用chat templateの暫定修正版をGGUFへ内包する。現行アプリと同じ
`chat_template_kwargs.enable_thinking`を送り、次を確認した。

| 確認 | 結果 |
|---|---|
| `enable_thinking=false` | reasoningなしで日本語本文を自然停止 |
| `enable_thinking=true` | reasoningと最終回答を別fieldへ分離 |
| assistant `{role, content}`を含む複数ターン | 例外なし、過去の合言葉を回答 |
| 現行`LlamaServerBackend`のstream | 本文とdone eventを正常取得 |

K2 Horizonで必要だった独自thinking fieldの補完はMiMoでは不要だった。GGUFの暫定templateが
上流で変更された場合は、この接続結果をそのまま再利用しない。

## 固定74〜75ページ

書籍ID 46の同じsource・prompt・seedを使い、途中の牢戻り発言より後の最大10年間の逃亡合意を
優先できるかを判定した。source SHAは
`7a44d23a1bdb263c7a67bcc3efa1405f1c3eeec33e076ff12efd3644e00e0f4e`、prompt SHAは
`4ce54b1fe01087b4b47eb584e8e630db88356541d90f76f64d899451b88bbeba`である。

| 条件 | 機械判定 | HTTP秒数 | 手動確認 |
|---|---:|---|---|
| thinkingなし | 2/3 | 8.6 / 4.2 / 5.0 | 失敗1件は理由とJSON判定が自己矛盾 |
| thinkingあり | 3/3 | 16.0 / 10.6 / 21.3 | 全件で最終合意・人物名・日本語根拠が妥当 |

thinkingありの生成速度はllama.cpp計測で約26.3〜28.8 token/秒だった。token生成自体は速いが、
reasoningが290〜560 tokenへ増えるため、固定ケースのend-to-end時間は現行Qwen3.6の過去測定
7.6〜8.5秒を上回った。runtimeが異なるため、これをモデル単体の厳密な速度順位とは扱わない。

## 追加52〜54ページ

候補推論前に固定済みの4主張をthinkingありで3 seed測定した。各試行とも自然停止しJSONを返したが、
機械判定はすべて3/4だった。

- seed 20260917 / 20260918: 翌日の外出を正しく`contradicted`としたが、固定oracleが要求する
  page 54を挙げず、実際の追跡行動があるpage 53だけを返した。
- seed 20260919: 従者の共犯は未確定だと理由に書いたが、statusを`insufficient`ではなく
  `contradicted`とした。
- 誘拐捜査経験と話者訂正は、全3試行でラベル・理由とも妥当だった。

従者設問はNex評価時にも`contradicted`と`insufficient`の境界が競合した既知の曖昧さがある。
そのため一般的な日本語性能の失敗数には数えないが、アプリの厳密なstatus・根拠ページ契約には不合格とする。

## 20ページ事実抽出

8〜27ページを、既存のBOOK_FACTS→CHARACTER_FACT二段階promptと現行アプリsamplingで評価した。

| 入力 / 出力 | 時間 | 終了 | reasoning / content |
|---|---:|---|---:|
| 16,678 / 8,192 token | 390.8秒 | `length` | 26,157文字 / 0文字 |

prefillは47.9秒・348.1 token/秒、生成は342.8秒・23.9 token/秒だった。BOOK_FACTSが得られず、
人物別抽出へ進まなかった。Nex mediumの同じ失敗は約244秒であり、MiMoは軽量でも
この長文契約の待ち時間を改善しない。32,768以上の出力、thinking budget調整、BF16原版は未測定だが、
現行8,192 tokenの事実抽出契約を満たさないため採用条件を変更しない。

## メモリと運用

短窓測定中のllama-server peak RSSは約11.4GB、長文後のRSSは約11.6GBだった。
長文後の`vmmap` physical footprintは2.2GB、mapped file residentは約8.9GBで、swapは0だった。
RSSとphysical footprintは定義が異なるため合算しない。64GB不足は見送り理由ではない。

評価用serverは停止済み。既存Ollamaを停止・変更せず、11441以外の接続先と本番データを変更していない。

## 採否

- 主生成・既定QA・書籍事実抽出・人物辞典: **不採用**。
- 現行Qwen3.6の置換: **しない**。
- 短窓thinking比較: 再評価用候補としてのみ保持可能。
- 独立verifier: Qwen3.5派生なので、異系統モデルを置く目的には優先しない。
- 画像・OCR: mmproj未取得・未評価であり、今回の結果から採否を決めない。

再評価は、8,192 token以内で20ページ抽出が自然停止するruntime/template更新、または
日本語小説・根拠ページ・strict statusを対象にした新checkpointが出た場合に限る。

## 保存証跡

ローカル評価ルート:
`/Users/medaro/.local/share/pic2pdf-llm/evaluations/2026-09-23-mimo/`

- `evaluation-manifest.json`: revision、重みsize・SHA、評価script・fixture SHA。
- `preflight.json`: thinking分離・複数ターン・HTTP疎通。
- `short-no-thinking/` / `short-thinking/`: 固定3 seedのrequest・raw・判定・memory。
- `fresh-thinking/`: 追加4主張のrequest・raw・機械判定。
- `long-thinking/`: 20ページ抽出のrequest・raw・停止結果。
- `manual-review.json` / `final-validation.json`: 手動意味確認と最終集計。
- `final-vmmap.txt` / `server-process.txt` / `swapusage.txt`: メモリ証跡。

raw本文は書籍データを含むため本レポートへ複製しない。
