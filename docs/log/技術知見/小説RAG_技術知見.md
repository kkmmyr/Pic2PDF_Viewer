# 小説RAG — 現行技術知見

> status: living | last-verified: 2026-10-05

本書は、現在のモデル・検索・運用判断へ短時間で到達するための要約である。
時系列のベンチマーク、失敗した候補、個別試行の数値は
[小説RAG 技術検証履歴](../../archive/検証/小説RAG_技術検証履歴.md)へ凍結した。
仕様は[データ設計](../../design/詳細設計/機能別/小説RAG_データ.md)、
[パイプライン設計](../../design/詳細設計/機能別/小説RAG_パイプライン設計.md)、
[検索QA設計](../../design/詳細設計/機能別/小説RAG_検索QA設計.md)を正本とする。

## 1. 現行推奨構成

| 環境・役割 | 現行選択 | 備考 |
|---|---|---|
| Windows/Linux 主生成・QA | Qwen3.6 35B-A3B + llama-server | 既定経路。長文は131,072 context、生成は直列 |
| Mac 主生成・QA | Qwen3.6 35B-A3B MLX | Apple Siliconのopt-in。公開前品質ゲートは同じ |
| 補助抽出・query expansion | Gemma 4 12B Ollama | MacでもMLXへ切り替えない |
| Embedding | bge-m3 | Ollama既定。Mac MLXはFP16 + CLS poolingのみ互換採用 |
| lexical検索 | SQLite FTS5 | 本番既定。page-level LanceDB ICUはshadow観測中 |
| dense検索 | bge-m3 chunk KNN | lexicalとのRRFを維持 |

モデル・backend・port・環境変数の値は
[小説RAG データ設計](../../design/詳細設計/機能別/小説RAG_データ.md)を正本とし、
本書へ複写しない。

## 2. 品質上の不変条件

- thinkingを有効にした事実だけでは品質を保証しない。自然停止、根拠、意味精度を別々に判定する。
- transport smoke、JSON parse成功、メモリ内ロード成功を本番品質合格として扱わない。
- 長文全体の入力が可能でも、終盤事実・主体・時系列の統合誤りは残る。
- 完成要約は構造検査だけで公開せず、主張単位の根拠照合と重要事実欠落検査を通す。
- 同じholdoutを調整と採用判定へ繰り返し使わない。
- OCR本文・索引・公開要約は別の成果物としてrollback可能にする。

## 3. Qwen運用

- Windowsの採用起動値は`-c 131072 -ncmoe 28`を基準とする。
- KV cache量子化とngram speculative decodingは速度改善に使えるが、意味精度を改善するものではない。
- `enable_thinking`、sampling、presence/repetition penaltyの転送漏れで品質と停止条件が変わる。
- M1 Max再評価では、思考なしの公式sampling相当`temperature=0.7 / top_p=0.8 / top_k=20`が
  固定ケース3/3、過去の`top_p=0.95 / top_k=40`は2/3だった。samplingをモデルと一緒に固定する。
- 1冊全文がcontextへ収まっても、一覧向け要約や人物同定は根拠検査を省略しない。
- Qwen3.8は抽出構造を部分改善したが、固定小説ケースではQwen3.6の完成要約を置換しない。

## 4. Apple Silicon MLX

- M1 Max 64GBではQwen3.6 35B-A3B、bge-m3、比較用30B級モデルを実行できる。
- bge-m3 MLXは`1_Pooling/config.json`でCLS poolingを固定する。mean poolingは不採用。
- Qwenと別生成モデルを同じcacheへ同時常駐・同時生成させない。
- Qwen3.8の`mlx-dspark`経路はQA・比較専用で、永続生成jobと自動公開を拒否する。
- 詳細な決定は[ADR-0019](../../design/基本設計/ADR/0019_apple-silicon-mlx-inference.md)、
  起動手順は[GPU環境セットアップ](../../design/環境構築/GPU環境セットアップ.md)を参照する。

## 5. 比較候補の現在判断

| 候補 | 判断 | 再評価する条件 |
|---|---|---|
| Gemma 4 12B MLX | 不採用 | 変換weight/template更新後にOllamaを非劣化で上回る |
| Qwen3.8-27B | 比較限定 | 根拠・意味・自然停止の固定ゲート合格 |
| Nemotron 75B | 不採用 | 固定小説ケースと長文根拠精度の改善 |
| Nemotron 30B | 不採用 | thinking効率と長文抽出精度の同時改善 |
| Ornith 1.5 35B-A3B | 不採用 | 20ページ入力で自然停止し、日本語意味ゲート合格 |
| Muse Glimmer 30B | 補助比較のみ | 短窓以外で現行役割を明確に上回る |
| Granite 4.2 30B Q4_K_M | 比較限定 | 固定小説ケースを3 seedすべてで合格し、長文初回待ち時間を改善 |
| Nex-N2.5-mini MLX 4-bit | 短窓比較限定 | 20ページ抽出を既存出力枠で自然停止させ、現行Qwenを上回る |
| K2 Horizon 36B-A4B MLX 4-bit | この構成では不採用 | 回答前終了・多言語混入・根拠誤読を解消し、templateと履歴互換を整える |
| MiMo V2.6 Distill Qwen 9B Q8_0 | 不採用 | thinkingありでも20ページ抽出を8,192 token以内に自然停止させ、厳密なstatus・根拠ページ契約を通す |
| llm-jp-4-33b-thinking Q4_K_M | 次期隔離評価候補 | 専用llama.cpp forkで固定・追加・20ページを通し、65K上限内の役割を特定する |
| llm-jp-4-32b-a3b-thinking | 速度優先の次点 | 33B denseより速度・品質の総合で優位になる |

64GB不足だけを不合格理由にしない。ロード可否、token速度、停止、形式、意味、根拠を分けて記録する。

Granite 4.2 30BはM1 Max 64GB上のOllama 0.32.12で、22GB・GPU 100%・32,768 contextとしてロードできた。
公式samplingの思考なしは固定ケース0/3、低思考は2/3、プロジェクト低温設定は0/3だった。
途中の「牢へ戻る」という発言を、その後の「最大10年間逃亡する」という最終合意より優先する誤りが再現したため、
現行Qwen3.6を置換しない。生成速度は固定ケースで約7.2〜7.5 token/秒、15,617 tokenの標準長文入力は
初回約360秒を要した。JSON形式と自然停止だけを採用根拠にしない。

## 6. 検索の現在判断

- dense大型化より先に、日本語lexical検索の0-hitを減らす。
- page-level LanceDB ICU BM25は固定20問と封印12問でFTS5を大きく上回り、個別Recall回帰0件だった。
- ただし本番切替はshadow実利用観測と利用者の別承認を残す。既定はFTS5のまま。
- ICU世代はSQLite全対象から完全再構築し、件数・ID・source hash・tokenizerをmanifestで検証する。
- stale、不整合、LanceDB例外時はFTS5へfail closedで縮退する。
- 正式契約と切替手順は[検索QA設計 §10](../../design/詳細設計/機能別/小説RAG_検索QA設計.md#rag-search-evaluation)と
  [ADR-0020](../../design/基本設計/ADR/0020_page-level-lancedb-icu-shadow.md)を参照する。

## 7. トラブルシューティングの順序

1. 入力文字数・token数・context上限・出力上限を分けて確認する。
2. backend、model、chat template、thinking、sampling、seedを記録する。
3. JSON/停止違反と意味不正解を別の失敗理由にする。
4. retrieval単体で正解ページが候補へ入るか確認してからLLMを疑う。
5. 公開前ゲート不合格時は候補を監査保存し、旧公開版を維持する。

## 8. 履歴を参照する場合

モデル別の実測、採否の詳細、過去の速度表、B-36の試行錯誤は
[小説RAG 技術検証履歴](../../archive/検証/小説RAG_技術検証履歴.md)を参照する。
履歴の数値を現在の推奨値として再利用するときは、runtime・model revision・hardware・
prompt・samplingが一致するかを再確認する。

## 9. Nex / K2 Horizon追加評価

Nexのmediumは短窓比較に限る。固定ケースは現行Qwenと同じ3/3だが、20ページ事実抽出は
公式sampling・現行アプリsamplingとも回答前に8,192 tokenへ到達する。書籍サマリ・人物辞典の
主生成を置換しない。noneは固定ケース2/3で、将来推測を現在の判定へ混ぜる誤りが残る。

K2のhighは固定ケース2/3で回答前終了があり、lowは終了タグを合わせると機械判定3/3になるが、
全件の多言語混入と1件の期間逆転が手動ゲートに落ちる。このMLX構成では採用しない。
K2の20ページ抽出は前段ゲート不合格のため未実施であり、長文性能を測定済みとは扱わない。
両モデルの`reasoning_effort`と現行Qwenの`enable_thinking`を混同せず、K2の独自思考タグと
assistant履歴のthinking fieldへモデル別に対応する必要がある。

MLX 0.32.0 / mlx-lm 0.31.3の推論スレッドでsamplingの乱数固定を再現し、初回品質結果は無効化した。
評価プロセスだけでimport時compileを外し、3 seedの出力差・同seed再現をHTTPで確認して再測定した。
通常Mac runtimeは未変更で、対処条件は[既知の問題](../既知の問題.md)を正本とする。
過去のMLX結果も同じ版・経路でseedに依存した判断は再検証する。

条件・限界・raw保存先は[Nex / K2評価記録](../../archive/検証/Nex_K2_Horizon_ローカルLLM評価_2026-09-18.md)を参照する。

## 10. MiMo V2.6 Distill Qwen 9B追加評価

M1 Max 64GBで公式ggml-org Q8_0をllama.cpp b10360、32,768 contextとして評価した。
現行`LlamaServerBackend`のthinking制御・stream・複数ターン履歴には接続でき、K2のような
assistant履歴field不足は再現しなかった。短窓固定ケースはthinkingなし2/3、thinkingあり3/3だった。

追加4主張は3 seedとも機械判定3/4で、意味を正しく説明しながら根拠pageまたはstatusを外した。
20ページ事実抽出は16,678入力token後、8,192 tokenをすべてreasoningへ使い、390.8秒・回答0文字で
`length`終了した。短窓生成は約26〜29 token/秒、server RSSは約11.6GB、swap 0であり、
メモリ不足やtransportではなく長文停止と厳密な根拠契約を見送り理由とする。

MiMo 9BはQwen3.5-9BをMiMoデータで調整したcheckpointなので、Qwen3.6に対する独立verifierの
系統差も小さい。主生成・既定QA・人物辞典へ配線せず、再評価は現行出力枠で長文を自然停止できる
runtime/templateまたは新checkpointが出た場合に限る。条件とraw保存先は
[MiMo 9B評価記録](../../archive/検証/MiMo_V2.6_Distill_Qwen_9B_ローカルLLM評価_2026-09-23.md)を参照する。

## 11. Qwen3.6 / MiMo同一入力再比較と次候補

Qwen3.6も全ゲート合格ではない。公式の思考なしsampling相当では固定ケース3/3だったが、
追加4主張の厳密契約は0/3、20ページ出力は話者・ページ帰属と重複の手動ゲートに落ちた。
ただし書籍・人物の両工程を合計176.4秒で自然停止し回答を返した。MiMoは同じ20ページ入力で
390.8秒後に8,192 tokenをreasoningへ使い切り回答0文字だったため、現行主生成はQwen3.6を維持する。

公式情報と利用者の日本語JSON抽出報告を照合し、次の品質優先候補を
`llm-jp-4-33b-thinking Q4_K_M`とした。Q4_K_Mは20.2GBでM1 Max 64GBへ収まる見込みだが、
65,536 context、専用llama.cpp fork、thinking parserが必要で、現行131K経路を直ちに置換できない。
まず短窓または独立verifierとして隔離評価する。速度優先の次点は32B-A3Bとする。

詳細な条件、raw保存先、公式・非公式資料は
[再比較・候補調査](../../archive/検証/Qwen3.6_MiMo_再比較・ローカルLLM候補調査_2026-09-23.md)を参照する。

## 12. Qwen3.8推論環境の隔離更新・再検証

MLX 0.32.3 / MLX-LM 0.32.0 / MLX-VLM 0.7.4 / MLX-dspark 0.20.2を隔離環境へ導入し、
DSparkの実HTTP契約を確認した。更新モデルrevisionはprocessor設定のみの変更で重みは同一。
通常回答は固定4問seed101で内容4/4だったが、同じ具体名問題でseed202・303とも「栗鼠」を欠落し、
3seedの当該問題は1/3。通常回答の拡大ゲートはNGで、46問・holdout・長文は実施していない。

引用4問seed101は本文一致4/4、表示後の要点4/4。ただしrawの要点は3/4で、具体名の回復は
既存の前後canonical本文補足による。引用一致だけで質問の充足・話者特定・複数seed安定性は保証できない。
本番API全体の検証やfreshな旧runtime A/Bは行っておらず、更新効果や本番採用を結論づけない。
Qwen3.8は比較限定を維持し、本作業で本番Qwen3.6・設定・DB/索引は変更していない。

条件、結果、保全証跡と未検証範囲は
[Qwen3.8更新再検証](../../archive/検証/Qwen3.8_MLXランタイム更新再検証_2026-10-05.md)を参照する。

## 13. Qwen3.8品質改善候補の適用条件

公式・利用者資料と固定runtimeを読み取り専用で調査した。更新後の低温QA条件は公式non-thinking組と異なる。
DSpark 0.20.2のDFlash/lookup分岐はpresence penaltyを生成関数へ渡さず、共通adapterはreasoning_effortを送信しない。
通常QA wrapperはthinkingを公開せず、引用QAはfalseを明示するため、設定追加だけでは比較が成立しない。
現在のREADMEの対応表より固定版の実装を優先し、baselineで転送・実効値を検証する必要がある。
前回presenceは0だったため、この制約だけで具体名欠落の原因を説明したことにはならない。

8bitの非公式KL測定は精度比較の理由になるが、日本語QAの正答率ではない。
根拠本文の短縮・配置、thinking low/medium、KV量子化なし・重み8bit、原文ID範囲による引用構成を
段階的な候補とする。過去のsampling調整やrerankerでも意味誤り・個別回帰が残り、万能策とはしない。
本調査で生成・取得・更新・実装・本番切替は行っていない。Qwen3.8は比較限定を維持する。

出典の強さ、互換性、比較順序と未検証範囲は
[Qwen3.8品質改善方法調査](../../archive/検証/Qwen3.8_品質改善方法調査_2026-10-05.md)を参照する。

## 14. Qwen3.8設定比較後の運用判断

公式non-thinking・thinking low/medium、非公式報告由来のT0.6、低温比較元を隔離baselineで実生成した。
低温条件は具体名問題の3 seedを通過したが、建物の質問で引用の改行変更・地の文引用形式の省略が残った。
内容充足、逐語引用、本文にない補足、全契約を別に採点し、設定変更だけで品質ゲート合格とはしない。
通常推論とDFlashのfreshな対照は未実施で、具体名回復をDFlashの不具合修正と結論づけない。
Qwen3.8は比較限定、現行Qwen3.6は維持する。現行QAはMLX経路のためOllama更新は直接の修正にならない。

固定MLX-VLM 0.7.4の通常continuous-batching経路はmin_pをHTTPで受理しても実samplerへ渡さない。
fallbackのstream_generate経路は別であり、全経路の無視とは一般化しない。
前回凍結調査の「通常samplerへ渡る」は誤記として新記録で訂正した。

次に引用方式を比較する場合は、本文の範囲IDからcanonical連続sliceを構成する候補を優先し、
質問充足・話者・未確認補足の検証を別に残す。8bitやKV量子化なしの改善は未実証として扱う。
実行条件、全22要求の判定、未実施範囲、訂正と保全証跡は
[公式・非公式設定比較](../../archive/検証/Qwen3.8_公式・非公式設定比較_2026-10-05.md)を参照する。
