# 小説OCR品質改善 実装計画

> status: active | last-verified: 2026-08-23 | owner: project owner
>
> 状態詳細: B-35正式holdoutの機械強制は完了、機械単独品質が未達
> 対象: Kindle小説画像のOCR、品質判定、Windows OCR agent、QA公開

過去の完了工程と実測値は
[OCR品質改善 技術知見](../技術知見/OCR品質改善_技術知見.md)へ移した。
現在の契約は [OCR設計書](../../design/詳細設計/機能別/OCR設計書.md)、
判定値は `scripts/maintenance/ocr_quality_policy.json` を正本とする。

## 1. 目的

文字・縦列・入力範囲の欠落を見逃さず、品質確認後だけ `novel.db` と検索索引へ公開する。
処理完走、機械品質、画像照合QA、公開整合性を別の完了条件として扱う。

## 2. 維持する禁止事項

- QA未承認本文を `books` / `pages` / `pages_fts` / LanceDBへ公開しない。
- Windowsから本番SQLiteを直接更新しない。
- 原画像を見ないLLM補正や辞書置換を自動で正本にしない。
- キャプチャPNGを前処理・再試行・学習素材生成で上書きしない。
- 表紙・挿絵・奥付を理由に通常散文の閾値を緩和しない。
- 固定標本や開封済みholdoutの改善値を、未知標本への性能として報告しない。

## 3. 現在地

| 項目 | 状態 | 判断 |
|---|---|---|
| ページ単位チェックポイントと再開 | 完了 | 入力SHAで合格済みページを再利用可能 |
| `awaiting_qa` と原子的公開 | 完了 | QA前に公開テーブルを変更しない |
| ページ種別・索引可否・補正文採用元 | 完了 | 不整合なQA更新はAPIで拒否 |
| 固定コーパス複合ゲート | 完了 | 値はpolicy JSON、項目別結果と終了コードを出力 |
| 第三OCR・oracle・PARSeq pilot | 診断完了 | 単独0.5%未達、本番モデルは未変更 |
| 3シリーズ30画面の診断 | 完了 | 集計CER達成、ページ最大・固有名詞で機械総合FAIL |
| Codex補助込み運用 | 条件付き合格 | 原画像QAの正解化実績であり機械性能ではない |
| 正式holdoutの機械的封印 | 完了 | 2026-08-17に30画面を一度だけ開封し、台帳へ記録済み |
| 公開縦書きscreening判定器 | 完了 | JSSODa-test / VJRODaの予測を完全性・digest・CERで再現可能に評価 |
| PaddleOCR-VL Apple Siliconスモーク | 完了 | JSSODa縦書き1〜4段の固定4枚で総合CER 0.3107%、最大0.6906%、列欠落0 |
| PaddleOCR-VL JSSODa縦書きscreening | fail-fast完了 | 79/1,125枚で総合CER 9.8305%、最大569.5767%。外れ値除外後も総合1.9573%、最大25.8567%のため不採用 |
| dots.mocr Apple Siliconスモーク | 通過 | JSSODa縦書き1〜4段とPaddleOCR-VL最大外れ値の固定5枚で総合CER 0.4654%、最大0.6614%、列欠落・反復0 |
| dots.mocr JSSODa縦書きscreening | fail-fast完了 | 79/1,125枚の最良layout版で総合CER 0.8990%、最大4.0155%。2.0% gate未達のため本番候補へ昇格しない |
| Unlimited-OCR Apple Siliconスモーク | fail-fast完了 | 固定5枚すべてで出力反復。総合CER 690.7200%、最大1,069.3122%のため79枚へ進めず不採用 |
| Nemotron Parse 2.0 MLX 8bitスモーク | fail-fast完了 | 通常promptと日本語decodeのruntime不整合を回避後も、固定1枚目で誤認文節が4,096 token上限まで反復したため拡大しない |
| Qianfan-OCR MLX 4bitスモーク | fail-fast完了 | 固定1枚目で最大CER gate超過、2枚目で生成反復したため不採用 |
| HunyuanOCR 1.5 BF16 llama.cppスモーク | fail-fast完了 | 固定1枚目は通過したが、2枚目の段落重複・順序入替で最大CER gateを超えたため不採用 |
| Hayai OCR v2 MPSスモーク | fail-fast完了 | 固定1枚目が8文字出力・CER 99.4932%だったため残り4枚へ進めず不採用 |
| Qwen3.5-OCR-JP-2B単体スモーク | fail-fast完了 | 固定5枚中4枚は総合CER 0.2416%だが、`001751`が8,000 token反復し、単体総合344.1829%のため不採用 |
| Qwen3.5 OCR + dots.mocr初期複合候補 | 15/79枚でfail-fast完了 | 総合CER 0.5166%、最大3.1042%。最大ページは反復・HTML切断なしでfallback不能のため自動公開候補として不採用 |
| Qwen3.5 OCR + dots.mocrレビュー版 | 導入準備中 | 開封済み79枚を完走し、Qwen 72枚・dots 7枚、総合CER 0.4091%、最大2.8835%。全ページQA前提で正式採用候補、worker統合と1冊pilotが残る |
| 機械単独・Codex省略 | 未完了 | 自動公開禁止を維持 |

## 4. Phase H1 — 正式holdoutをfail closed化する

### 実装

1. B-35用manifest schemaへ `series_id`、用途、固定日時、画像SHA、package digestを持たせる。
2. 選定時に3シリーズ以上、通常散文20画面以上、固有名詞10語・50出現以上を検査する。
3. 候補品質を参照せず選定したことを、選定入力と出力digestで再検証できるようにする。
4. holdout台帳へ `sealed` / `opened` / `retired_to_tuning` を記録し、`opened` の再評価を既定拒否する。
5. seed・画像QA完了後にformal manifestを封印し、benchmarkは同じmanifestの全package digestを使う。
6. formal manifestは選定全件のrun・page・画像SHA・reference SHA・package SHA集合を検査する。
7. overrideは通常benchmark経路へ設けず、開封済みの再利用を常に拒否する。

2026-08-17に`b35-holdout-v1`と`b35-holdout-ledger-v1`を実装した。seal CLIは
quality-blind選定入力・出力digest、policy digest、3シリーズ、20 normal prose、固有名詞条件、
全packageを検査する。benchmarkはengine起動前に`opened`をatomic記録し、失敗後もsealedへ戻さない。
汎用benchmarkはformal引数なしで従来動作を維持する。

### 受入条件

- 2シリーズ、19画面、固有名詞不足、SHA差し替え、package一部欠落を各々終了コード非0で拒否する。
- 開封済みmanifestを再利用すると、明示overrideなしでは処理を開始しない。
- 同じ入力から同じdigestが再生成され、1 byteの変更で不一致になる。
- 既存の汎用コーパスbenchmarkはB-35専用項目なしでも従来どおり実行できる。
- unit testとCLI integration testで、DB・画像・公開本文を変更しないことを確認する。

## 5. Phase H2 — 評価比較器の契約を分離する

B-35 benchmarkと `ocr_ground_truth` APIは正規化・用途が異なる。共通化は「同じCER」という
名前だけで行わず、次の境界を固定する。

### 実装

- benchmark用正規化、編集距離、列欠落、固有名詞評価を専用moduleへ集約する。
- API表示用CERは現在のUI契約を維持し、benchmark comparatorへ暗黙に切り替えない。
- JSON schema、浮動小数丸め、空文字、改行、約物、Unicode正規化のgolden fixtureを用意する。
- evaluator versionとpolicy digestをレポートへ保存する。

### 受入条件

- 既存監査JSONを再評価し、意図した変更がない限り同じ判定を再現する。
- APIの代表fixtureは変更前のCER表示と一致する。
- comparatorの差があるfixtureは、双方の期待値と非互換理由をテスト名で明示する。

## 6. Phase H3 — 未調整holdoutで機械候補を再評価する

H1完了後に新しい未調整holdoutを封印し、閾値や選択規則を変更せず一度だけ評価する。

### 評価対象

- 現行primary / external
- 配布NDLOCR-Liteと採用候補モデル
- 文字位置合議と候補支持付き固有名詞補正
- 新しい列欠落検出・部分再OCRを実装した場合は、その固定版

### 受入条件

policy JSONの全ゲートを同時に満たすこと。加重CERだけの合格、oracle、Codex補正文、
ground truth自身との比較を機械合格へ混ぜない。不合格なら同じholdoutで調整せず、
`retired_to_tuning`へ移して次の仮説を立てる。

2026-08-17の未調整holdoutでは、現行primaryを3シリーズ30画面で一度だけ評価した。
通常散文CER 27.4038%、ページ最大496.7509%、列欠落疑い3画面、固有名詞324/430
（再現率75.3488%）で総合 `FAIL` だった。最大外れ値の反復出力1画面を除外しても
通常散文CERは3.8608%であり、0.5%基準には未達である。同じholdoutは再評価せず、
保存済みレポートを調整用の原因分析にだけ使用する。

開封後の調整用集計では、保存済み選択結果の通常散文CERは4.1626%だった。既存QAリスク条件
（primary 256文字以上、externalが30文字かつ2%以上長い）を候補選択へ共有し、反復のない
externalを必須QA候補にする固定版は4画面を切り替え、CER 2.1141%、ページ最大10.1805%、
列欠落疑い1画面、固有名詞再現率82.5581%まで改善した。これは開封済みholdoutを使った
調整値であり、正式合格や未知データへの性能値には数えない。

第三候補としてYomiToku検出＋MangaOCR認識を30画面へ適用したが、単体CER 70.6753%、
3候補文字合議CER 2.4693%で固定版を改善しなかった。正解参照の3候補ページoracleも
CER 1.4761%、ページ最大10.1805%であり、現候補集合だけでは0.5%へ到達できない。
開封済みデータに合わせた追加閾値は導入せず、上記固定版を新しい品質非参照holdoutへ送る。

2026-08-18に公開最新版NDLOCR-Lite v1.2.3も調整用に再評価した。単体CER 3.1832%、
3候補文字合議CER 1.1174%で、列欠落疑いは0画面になったが、ページ最大5.3345%と固有名詞
再現率91.8605%が残った。productionへ常時追加せず、まずprimary異常反復時に反復のない
externalへ切り替える必須QAフォールバックを固定した。この規則は最大反復ページを除去したが、
次の正式評価前に行bboxを用いる部分再OCRまたは固有名詞候補支持の改善がなお必要である。

行bbox部分再OCRは最悪ページでCER 3.1769%まで改善したものの、別難例で38.6997%へ悪化し、
group size 1・2・4にも単調な品質関係がなかったため自動選択へ入れない。llama.cpp requestは
`seed=0`へ固定し、同一候補本文が3回一致することを確認した。次の固定候補は、部分再OCRを
QA補助に留めたまま、固有名詞候補支持または別認識器でページ最大値を下げる必要がある。

候補支持型固有名詞補正は、公式シリーズ台帳と同位置の独立OCR完全一致を必須条件として
30画面で評価した。調整用正解の「鳥妃」5出現を原画像・公式表記どおり「烏妃」へ訂正した
別記録上では、通常散文CER 1.1346%から1.0622%、固有名詞再現率91.8605%から96.0465%へ
改善し、21補正・10画面は全件改善、悪化0だった。ただしページ最大5.3345%は変わらない。
PP-OCRv6 mediumも最大CER画面で全文33.6462%、NDLOCR行bbox再利用11.6968%だったため、
拡大評価しない。次の未調整holdoutを消費する前に、固有名詞補正を維持しつつ、小書き文字・
約物を保持してページ最大値を下げる独立候補がなお必要である。

2026-08-22の公開情報再調査では、次の独立候補を`PaddleOCR-VL-1.6`、次点を`dots.mocr`とした。
前者はPP-OCRv6認識器とは別系統の0.9B文書VLMで、後者は3Bの多言語文書VLMである。ただし両者の
公開総合benchmarkはKindle縦書き日本語の小書き文字・約物精度を直接保証しない。新holdoutはまだ
封印せず、まず公開の縦書き日本語JSSODa-test / VJRODaで方向・列順をscreeningし、通過版だけを
開封済み30画面へ固定prompt・revision・seedで適用する。ページ最大CER 2.0%未満、列欠落疑い0、
固有名詞・約物の非劣化を同時に満たした場合だけ、品質非参照の新holdoutを封印する。

公開screeningは`scripts/maintenance/ocr_benchmark_vertical_screen.py`を正規入口とする。
JSSODa-testでは縦書きだけを既定対象とし、列数別の加重CER、ページ最大CER、完全一致率を出す。
VJRODaでは実文書全件を同じ正規化・CER契約で評価する。metadataとpredictionのID重複、欠落、
余剰IDをfail closedで拒否し、両入力のSHA-256、model revision、prompt ID、seedをレポートへ固定する。
反復除去は行わず、生成系OCRの異常も候補品質として残す。これは候補のfail-fast判定であり、
B-35正式holdoutの代替にはしない。

Macでの実行は公式Apple Silicon手順に従い、完全なPaddleOCR-VL pipelineとMLX-VLM serviceを
別process・別virtual environmentで構成する。VLM component単体のHTTP呼び出しは完全pipelineの
精度を再現しないため採用しない。最初は1並列・固定revision・固定seedで実行し、GPUを他用途が
使用中の間はmodel download、service起動、推論を行わない。

2026-08-23にM1 Max 64GBで、`PaddlePaddle 3.2.1`、`PaddleOCR 3.7.0`、
`PaddleX 3.7.2`、`MLX-VLM 0.6.15`を別のPython 3.12環境へ導入した。VLMは
`PaddlePaddle/PaddleOCR-VL-1.6`のrevision
`c5630abae1d940eafe0697512a0325494b02ab42`、レイアウト解析は`PP-DocLayoutV3`を使う。
JSSODa-test revision `b38c3f83cf627a72afb1652640141ffbf81bedd6`から縦書き1〜4段を1枚ずつ
固定したスモークでは、4枚2,897文字の総合CER 0.3107%、ページ最大0.6906%、列欠落0だった。
clientの最大RSSは約2.43GiB、MLX serviceの常駐RSSは約1.9〜2.1GiBで、メモリ圧迫は発生しなかった。

`mlx-vlm==0.6.15`だけではchat template用`jinja2`が導入されず、service再起動前はHTTP 500に
なるため、検証環境では`jinja2==3.1.6`を明示依存とする。PaddleOCR CLIの`save_all()`は推論後に
Word出力まで試みて`python-docx`未導入で失敗するため、全件screeningはPython APIからJSONだけを
回収する。予測JSONLは1ページ成功ごとにflushし、既存IDの重複、入力画像欠落、空本文、metadata外IDを
fail closedで拒否する。同じmodel revision、prompt ID、seed、入力画像SHAの場合だけ再開を許可し、
screening完了後に既存の`ocr_benchmark_vertical_screen.py`で全ID完全性とCERを判定する。
性能調整では、公式の1:1 client / service推奨に従ってVLM同時要求数と入力ページbatch数を独立に記録する。
複数ページを1回のpipeline呼び出しへまとめる場合も、結果件数と入力順を検査してから各ページを個別に
fsyncする。batch途中のservice失敗では未保存batchだけを再実行し、既存checkpointは変更しない。
1並列との差分が本文完全一致し、メモリ圧迫・service errorがなく、実測短縮する設定だけを全件へ使う。

固定4枚の比較では、VLM同時要求4・ページbatch 1は推論18.62秒で1・1の18.76秒と実質同等だった。
VLM同時要求4・ページbatch 4は19.02秒で短縮せず、4枚中1枚で読点1文字が欠落して本文完全一致にも
失敗した。client最大RSSも約1.1GiBから約2.36GiBへ増えたため、JSSODa全件は同時要求1・
ページbatch 1へ固定する。並列値とbatch値はcheckpoint provenanceへ保存し、異なる設定を混在させない。

同時要求1・ページbatch 1の本screeningは、79/1,125枚をcheckpointした時点でfail-fast終了した。
総合CER 9.8305%、ページ最大569.5767%、完全一致率7.5949%だった。最大外れ値`001751`は、罫線で
3領域に分かれた正常な縦書き画像に対し、MLX-VLMが同一句を生成上限まで反復した。外れ値1枚を
除外しても78枚の総合CERは1.9573%、ページ最大は25.8567%で、1・2・4段にも23%以上の難例がある。
メモリは十分に空いていたため64GB unified memory不足ではなく、モデル・layout・生成経路の品質問題と
判断する。公式APIが提供する`repetition_penalty=1.1`と`max_new_tokens=1024`でも同ページは反復し、
CER 125.6614%だった。MLX-VLM 0.6.15は既知のPaddleOCR-VL batching修正を含む版であり、1並列でも
再現するため、並列バグの回避だけでは解消しない。VJRODaと開封済み30画面へは進めず、次候補の
`dots.mocr`を公開screeningから評価する。異常出力は診断artifactとして保持し、本番本文へ補正採用しない。

公開情報との照合では、[PaddleOCR-VL公式ガイド](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PaddleOCR-VL.en.md)
が`repetition_penalty`と`max_new_tokens`を調整可能としている一方、値だけで品質回復する保証はない。
MLX-VLMでは長文OCRが生成上限まで反復し、通常のrepetition penaltyで止まらない
[別OCRモデルのconfirmed issue](https://github.com/Blaizzy/mlx-vlm/issues/1021)も報告されている。
PaddleOCR-VLの連続batchで古いmRoPE状態を再利用する問題は
[PR #1285](https://github.com/Blaizzy/mlx-vlm/pull/1285)で修正済みで、今回の導入版にも修正箇所が存在する。
したがって、未修正batching issueだけを原因とする扱い、しきい値変更、反復部分の後処理削除では採用へ戻さない。

次候補の`dots.mocr`は、公式model revision
`e539fbb52280393adc081b289ec597430a0f9031`をM1 Max 64GB上の`MLX-VLM 0.6.15`でBF16のまま
読み込み、公式`prompt_ocr`の`Extract the text content from this image.`、temperature 0.1、top_p 1.0、
seed 0、最大2,048 token、単ページ実行へ固定する。モデルはcustom Transformers codeを含むため、固定snapshot内の
Python 3ファイルを監査し、明示許可した検証CLIだけで`trust_remote_code=True`を使う。processor初期化には
`torch 2.7.0`と`torchvision 0.22.0`が必要だったが、推論本体はApple Silicon GPUのMLXで動作する。

JSSODa-test縦書き1〜4段の固定4枚と、PaddleOCR-VLが生成反復した`001751`を加えた5枚3,653文字の
スモークでは、総編集距離17、総合CER 0.4654%、ページ最大CER 0.6614%、列欠落・生成反復0だった。
モデルを1回だけ読み込んだ5枚推論は68.36秒、process最大RSSは約6.87GiB、MLX peak memoryは約9.15GBで、
64GB unified memoryは制約にならなかった。この段階では方向・列順・難例耐性の予備gateを通過しただけであり、
公開screeningを通過するまで本番候補へ昇格しない。

単純な`prompt_ocr`による先頭79/1,125枚のscreeningは、総合CER 1.6402%、ページ最大26.9289%だった。
罫線で分割された`000918`と`001293`では最下段を省略し、`000639`では段落順を入れ替えた。
公式が一般文書解析に推奨する`prompt_layout_all_en`へ切り替え、bbox・category・textのJSONを検証して
モデル出力順に本文を結合すると、この3枚は最大1.9093%まで回復した。79枚全体も総合CER 0.8990%へ
改善し、JSON失敗・列単位欠落・生成反復は0だった。平均12.40秒/枚、process最大RSS約6.93GiB、
MLX peak memory約9.50GBで、64GB unified memoryには十分な余裕があった。

ただしlayout版もページ最大CER 4.0155%で、1〜4段の各group最大が2.4390〜4.0155%となり、
既定の2.0% gateを満たさなかった。上位5難例のtemperature 0再生成でも最大4.0155%は変わらず、
最大難例をlayout bboxごとにcropして再OCRする二段階方式は4.0155%から5.6995%へ悪化した。
原因はメモリ、出力上限、サンプリング、領域欠落ではなく、通常の文字誤認識がページ内に累積する
モデル品質と判断する。全1,125枚、同一画面3回、VJRODa、開封済み30画面へは進めず、
モデルまたはMLX実装の更新時に同じ79枚と固定artifactから再開する。

2026-08-23の再調査では、次の独立候補を`sbintuitions/sarashina2.2-ocr`とする。
日本語・英語文書向けのend-to-end OCRで、公式model cardはVJRODaの縦書き読順を含む評価において
旧dots.ocrより低いCERを報告している。ただしdots.mocrとの直接比較ではなく、Kindle小説での
ページ最大CERも未確認なので、公開値だけで本番候補へ昇格しない。

評価はMIT licenseのBF16重みとrevision`eafb8d48cb2f2a3a6dce571d26b26586ff048fda`を固定し、
公式Transformers 4.57.1設定、temperature 0、top_p 0.95、repetition penalty 1.2から開始する。
公式手順はCUDAであり、Mac MPSは未保証なので、まずJSSODa固定5枚でload、本文、読順、反復、
処理時間、RSSを診断する。custom code 3ファイルは固定snapshotで監査し、ネットワーク、subprocess、
任意ファイル操作のimportがないことを確認したが、`trust_remote_code=True`は隔離評価CLIだけに許可する。
非公式検証で推奨penalty 1.2の生成loop報告があるため、既存の反復検査を無効化せず、loop時は不合格を
正本とする。penalty 1.3は原因診断として別runに限り、改善値を公式設定の結果へ混ぜない。

固定5枚が総合CER 0.5%以下、ページ最大2.0%未満、列欠落・反復0を満たした場合だけ、dots.mocrと
同じ先頭79枚へ進む。79枚でもページ最大2.0%未満を満たした場合だけ全JSSODa、VJRODa、
開封済み30画面の順で進み、新しい未調整holdoutはその後まで封印しない。Markdown記号をCERのために
恣意的に削除せず、モデルのraw textを既存の共通正規化へ渡す。

image-onlyで正しい文字起こしの後に要約・箇条書きを付加するpageが出た場合、Markdown除去や
first-block切出しでは救済しない。「文字起こし本文だけ」を明示するtext promptを別prompt IDで
当該page→固定5枚の順に診断し、改善した場合も79枚を新規runで再評価する。

2026-08-23実測では固定5枚を総合CER 0.2190%、最大0.9259%で通過したが、先頭79枚runは71枚時点で
総合0.8385%、最大100%となりfail-fast終了した。`001626`は317文字の文字起こし部分が完全一致した後、
同内容の要約箇条書きを付加して634正規化文字になった。明示text promptでも649 raw文字の出力が
image-onlyと完全一致しCER 100%だった。first-block切出しは一般ページの段落境界と区別できないため
採用せず、Sarashina2.2-OCRは本番候補から外す。71枚は3,266.33秒、最大RSS約16.42GiB、peak memory
footprint約54.28GiB、swap 0であり、失敗原因を64GB unified memory不足とは判定しない。

追加調査した`yuta1984/ndlocrlite-web`の2026年4月再学習PARSeq 3モデルは、8月18日に評価済みの
公式NDLOCR-Lite v1.2.3と30・50・100文字版のSHA-256がすべて一致した。派生Web実装にも24px入力の
公開モデルへ16px shapeを指定する不整合があるため、新しい独立候補として再評価しない。
`honmono-ocr`も公開benchmarkは縦書きを含むが、参照コードが404、モデルが認証なしで取得不能のため、
固定実装を再現できる候補へ数えない。

次候補はBaiduの`Unlimited-OCR` 3Bとし、公式MLX-VLM実装、MITのBF16変換
`mlx-community/Unlimited-OCR-bf16` revision`6d9f675e3fa73dd49cd03f630868b1941c72803f`を固定する。
公式のsingle-page基準prompt `document parsing.`、temperature 0、モデル固有後処理なしから開始する。
raw textをそのまま共通正規化へ渡し、反復本文や誤認識を後処理で削除しない。
JSSODa固定5枚で総合CER 0.5%以下、ページ最大2.0%未満、列欠落・反復0の場合だけ、同じ先頭79枚へ進む。

固定5枚の実測では全ページが生成上限まで反復し、3,653正解文字に対して正規化後の総合CER
690.7200%、ページ最大1,069.3122%、完全一致0%だった。5枚推論は144.00秒、process最大RSS
約7.42GB、peak memory footprint約13.44GB、swap 0であり、64GB unified memory不足とは判定しない。
公開screening gateを固定5枚で不合格としたため79枚へ進めず、Unlimited-OCRを本番候補から外す。
反復を隠すno-repeat n-gramや重複削除を採用値へ使わず、必要なら生成loopの原因診断だけを別runにする。

次にNVIDIA `NVIDIA-Nemotron-Parse-2.0`を調査した。公式モデルは約903M parameterで
CJKを含む多言語改善を謳うが、日本語縦書き固有値はない。MLX変換は
`mlx-community/Nemotron-Parse-2.0-8bit` revision
`e7e89479657fb3631028ac12b6bc0d5a59ceafe4`を固定した。4bitは変換元の公開試験で
表の反復回帰があるため使わない。変換cardのApache-2.0表記に依存せず、元モデルの
OpenMDW License Agreement 1.1と、同梱tokenizerのCC-BY-4.0を利用条件の正本とする。

MLX-VLMの通常文promptでは`<<<<`反復となり、元実装の専用task token列
`</s><s><predict_bbox><predict_classes><output_markdown><predict_no_text_in_pic>`が必須だった。
さらに標準のBPE streaming detokenizerは日本語token `キ`で`KeyError`になるため、
評価時だけ`NaiveStreamingDetokenizer`で一括decodeした。それでもJSSODa固定先頭
`000006`は誤認文節を4,096 token上限まで反復し、42.40秒、process最大RSS約2.20GB、
peak footprint約41.66GB、swap 0だった。メモリ不足ではなく日本語縦書き品質の不合格とし、
残り4枚と79枚は実行しない。反復削除、強制停止processor、本文切出しで採用値を救済しない。

次の独立候補はBaidu `Qianfan-OCR`とする。公式model cardは4B-parameterモデルと説明し、
配布safetensors metadataは4,741,408,256 parameter（Hugging Face表示は5B）である。Apache-2.0、192言語対応、
`do_sample=False`と`Parse this document to Markdown.`を基準経路として示すが、日本語縦書き小説の
ページ最大CERは公開していない。Apple Siliconでは
`jason1966/Qianfan-OCR-MLX-4bit` revision
`125a392cc25e8750f427c7e09b5a517f07bbf70c`を固定し、MLX-VLM 0.6.15で評価する。
変換configは元Baidu checkpoint revisionを保持しないため、公式BF16との同一性や変換cardの
「精度低下なし」を前提にせず、4bit版自体を独立候補として扱う。

実行前に同梱custom Pythonを監査し、model、prompt、画像SHA、engine version、生成設定、raw textを
fsync checkpointへ残す。temperature 0、最大4,096 token、後処理なしで固定5枚を評価し、総合CER
0.5%以下、ページ最大2.0%未満、列欠落・反復0を満たした場合だけ先頭79枚へ進む。Markdown記号や
Layout-as-Thoughtは初回採用値から除外せず、追加説明・思考・反復が本文へ混ざれば品質不合格とする。

固定5枚runは2枚目でfail-fast終了した。`000006`は592正解文字に対し588予測文字、CER 2.0270%で
ページ最大2.0%未満のgateを単独で超えた。`000142`は913正解文字に対し7,321予測文字、CER
753.8883%となり、末尾で「決して許されることは」を反復した。2枚の完了時間は14.57秒と80.44秒、
3枚目を停止するまでのprocess最大RSSは約3.51GiB、peak footprint約6.90GiB、swap 0だった。
64GB unified memory不足ではなく日本語縦書きの認識・読順・生成反復の不合格とし、残り3枚と
79枚は実行しない。4bit版のpenalty追加や反復切出しで採用値を救済せず、本番候補から外す。

続けてTencent `HunyuanOCR-1.5`を評価した。公式はPC・consumer GPU向けllama.cpp経路と、
temperature 0、top_p 1、top_k無効、repetition penalty 1.08を明示する。Apple Siliconでは
llama.cpp build `b10360-48d22e295`と、`prithivMLmods/HunyuanOCR-1.5-GGUF-Updated`
revision`9ddd3b47beb0de305ecd89a717748bac080d7aee`のBF16本体・projectorを固定した。
派生repoのApache-2.0 metadataには依存せず、元モデルのTencent Hunyuan Community Licenseを
利用条件の正本とする。派生repoは元Tencent revisionを保持しないため、BF16 GGUF自体を候補として判定する。

公式文書解析promptで`000006`は592文字中2文字誤り、CER 0.3378%、欠落・反復0で通過した。
しかし`000142`は同一段落を二重出力して段落順も入れ替わり、913正解文字に対して1,030予測文字、
CER 13.0340%だった。2枚総合CERは8.0399%。2枚目は14.57秒、process最大RSS約14.34GiB、
peak footprint約13.28GiB、swap 0だった。ページ最大2.0%と列欠落・重複gateに不合格のため、
残り3枚と79枚は実行せず、本番候補から外す。段落重複除去や順序並べ替えで採用値を救済しない。

次候補は`JustANormalTinkerer/hayai-ocr-v2`とする。固定revisionは
`fa1ca12bacba3ac09a9fee09c6086ef84c72d8f4`、Apache-2.0、F32重み622,500,080 byteである。
SigLIP2 NaFlexと約0.2Bの独自causal decoderで、text detectorを介さず全画像からgreedy生成する。
一方、公式finetuning setは約2,000件の短い漫画crop、公開例は最大256 patch・128 token、公式平均CERは
8.52%であり、592文字以上の小説ページを保証しない。`configuration_hayai.py`と
`modeling_hayai.py`を固定revisionで監査し、外部書込み・subprocess・任意コード評価がないことを確認後、
公式repetition penalty 1.20、最大1,024 token、JSSODa固定`000006`だけをMPSで診断した。最大token変更は
ページ全文を収めるための出力budgetであり、本文dedupe・再認識・samplingは加えていない。

実測では592正規化文字に対して「「Incle」の」の8文字だけを生成し、距離589、CER 99.4932%だった。
推論2.30秒、process最大RSS 1,710,555,136 byte、MPS driver allocation最大観測1,552,662,528 byteで、
64GB unified memory不足ではない。ページ最大2.0%未満と列coverageのgateに不合格のため、残り4枚と
79枚へ進めず本番候補から外す。短文crop、回転、patch数変更による同一モデルの救済は行わない。

fail-fast不採用のNemotron ParseとHunyuanOCRは一回限りの隔離実行で結果・revision・hashを記録済みのため、
専用runnerを恒久資産として追加しない。Qianfan runnerはcustom code fingerprintとMLX runtime差分を再診断する
期限付き資産として2026-11-16まで保有する。Hayaiは実測・環境を文書へ残し、再実行CLIを追加しない。

Hayai終了後に`ebinan92/Qwen3.5-ocr-jp-2b`を評価した。固定revisionは
`dc58acc05962cb2ca129c8d3533ab7e5a651cc02`、Apache-2.0、BF16 2,782,629,184 parameterである。
公式cardは日本語縦書き・ルビを学習重点とし、VJRODa 92件でCER 7.3%を報告する。これはB-35の
0.5%基準を保証しないため、未調整holdoutではなくJSSODa固定5枚からfail-fastする。

標準Transformers Qwen3.5実装をPyTorch MPS BF16で使い、公式固定prompt
`OCR this image as HTML layout blocks with bbox and label.`、`do_sample=False`、最大8,000 tokenとする。
HTMLはDOM順の可視文字だけを抽出し、rubyの`rt`は本文へ混ぜない。tag・attribute・単一code fence除去は
出力protocolの復号であり、block順序変更、本文dedupe、言語補正は行わない。raw HTMLと抽出本文をともに保存した。

固定5枚のうち`000006`は距離1・CER 0.1689%、`000142`は距離0・CER 0%、`000158`は距離5・
CER 0.6906%、`000609`は距離1・CER 0.1497%で、先頭4枚総合は距離7/2,897文字・CER 0.2416%だった。
一方、`001751`は同一文節を最大8,000 tokenまで反復し、756正解文字に対して13,190予測文字、距離12,566、
CER 1,662.1693%となった。固定5枚単体総合は距離12,573/3,653文字・CER 344.1829%であり、Qwen単体は
生成反復gateにより不採用とする。最初のmodel loadを含む最大RSSは3,408,150,528 byte、MPS driver allocationの
最大観測は6,069,567,488 byteで、swap増加はなかった。64GB unified memory不足ではなく生成停止品質の問題である。

既存の`has_suspicious_repetition`を抽出本文へ適用すると、固定5枚では正常4枚が全てfalse、`001751`だけがtrueだった。
そこで参照正解をselectorへ渡さず、反復または最大token到達によるHTML末尾切断なら同じ固定dots.mocr候補へ
切り替え、それ以外はQwenを選ぶ。dots.mocrの
過去固定5枚実測は各ページCER 0.6614%以下なので、756文字の`001751`の距離は5以下である。Qwen正常4枚の距離7と
合成した複合候補は距離12以下/3,653文字、総合CER 0.3285%以下、ページ最大0.6907%以下となり、固定5枚gateを通過する。
これは保存済み集計値から導いた上界で、dotsのraw予測を復元した再計測値ではない。selectorはQwen側の反復flagを
再計算し、HTML切断、画像SHA、fallback過不足をfail closedで検査する実装へ固定した。

同じ品質blind規則の固定79枚screeningは、15枚をcheckpointした時点で総編集距離53/10,259文字・
総合CER 0.5166%、ページ最大3.1042%となったため停止した。最大ページ`000260`は451正解文字に対して
447予測文字、距離14で、縦書き中の半角`AI`を5箇所とも助詞「と」に誤認し、ほかにも約物・文字誤りがあった。
反復もHTML末尾切断もないため固定selectorではQwenが選ばれ、dots fallbackで救済できない。メモリ・生成停止ではなく
通常文字認識の品質不合格であり、正解を見て`AI`やページIDを追加fallback条件へ使わない。固定79枚の残り64枚、
VJRODa、正式holdoutへは進めない。

同じ`000260`をMPS BF16でさらに2回再実行すると、本文とraw HTMLは3回すべてbyte一致した。さらに
同じsource重みをMLX-VLM 0.6.15でBF16変換し、公式prompt・temperature 0で評価しても距離14・CER 3.1042%で、
`AI`5箇所の誤認は共通だった。PyTorch MPSの揺らぎやruntime固有誤差ではなく、固定モデルの認識誤りとする。

一方、Qwen raw HTMLは`000260`だけ誤認箇所4つを`<i>`で囲み、他の先頭14枚には`div` / `p`以外の
可視markupがなかった。本プロジェクトはplain textへ復号して装飾を保持しないため、`div` / `ruby` / `rt` / `p` / `br`
以外のinline markupをcandidate-onlyの保守的fallback signalとするv2を診断する。これは開封済み公開screeningで
発見した調整版なので固定5枚合格値や正式性能へ遡及適用せず、dots.mocrの`000260`実測と同じ79枚の再screeningを
通過した場合だけ次候補に数える。`<i>`本文を`AI`へ置換する補正は行わない。

v2 selectorは既存15枚から`000260`だけをfallback対象にした。dots.mocr固定revisionのBF16 layout版は
同ページで距離10/451文字・CER 2.2173%となり、`AI`5箇所をすべて「は」と誤認した。15枚複合総合は
距離49/10,259文字・CER 0.4776%へ改善したが、ページ最大2.2173%で既定2.0%未満を満たさない。
事前条件どおり残り64枚を再実行せず、v2も本番候補から外す。`<i>`を`AI`へ置換する補正や、Qwenとdotsの
誤認「と」/「は」から正解を推測する合議は導入しない。

## 7. Phase H4 — レビュー前提laneと確認縮小の段階評価

ADR-0022により、Qwen＋dots複合版はH3の機械総合不合格でも全ページ画像照合を条件に導入できる。
このlaneではQwenとdotsを全ページ生成し、全ページを`required`とする。narrativeは両候補本文と原画像を
比較して必要箇所を
`corrected_text`へ保存する。未修正予測と修正後本文を別集計し、全ページ承認まで公開しない。

開封済みJSSODa縦書き79枚のレビュー版は、反復・HTML切断4枚、非保持markup 1枚、隣接狭列の
bbox読順違反1枚、dotsの有意な文字量増加1枚をdots初期候補へ切り替えた。総編集距離223/54,504文字、
加重CER 0.4091%、最大2.8835%で、総合gateだけを通過した。Qwen単体は反復4/79枚・総合104.9354%、
反復4枚を除いても1.2886%、dots単体は0.8990%・最大4.0155%だったため、Qwen主候補＋dots副候補を維持する。
候補間のID・画像SHAに加えて、各候補のrevision・fingerprint・promptが全ページ同一であることを検証する。
この値は開封後にsignalを調整したscreening値で、H3または未調整holdoutの合格値へ数えない。

Codex確認の縮小または自動公開は、従来どおりH3の機械総合合格後にだけ着手する。

1. 同一画面3回で判定と差分が一致することを確認する。
2. 100画面連続で構造化出力成功率99%以上、timeout・未回収process 0を確認する。
3. `normal_prose` かつ既存リスクflag 0に限定し、Codex確認を全件から標本監査へ縮小する。
4. 初期は10%を無作為監査し、重大な欠落・意味変更・分類誤り1件で全件確認へ戻す。
5. モデル、prompt、画像切り出し、CLIの変更ごとに版を分けて再評価する。

## 8. Phase H5 — 公開ロールバックと障害注入

OCR品質が合格しても公開処理の安全性は別に検証する。

- subprocess hang、malformed JSON、部分ページ結果、heartbeat timeout
- QA更新途中のDB例外、FTS同期失敗、公開transaction rollback
- backup失敗、ディスク不足、同一runへの競合承認

各障害で、旧公開本文・FTS・`ocr_done_at`が保持され、runが説明可能な失敗状態になり、
再試行が重複公開を起こさないことを確認する。共通の副作用契約は
[R0〜R7 リファクタリング契約表](../../archive/リファクタリング契約表_R0-R7.md) を参照する。

2026-08-22の監査では、未完走runの公開拒否、malformed Surya出力の品質不合格、workerの
ページ単位失敗継続、新規書籍の公開transaction rollback、既存版への手動rollback、FTS再構築を
既存testで確認した。一方、既存canonical本文を置換するtransactionの途中失敗、rollback操作自身の
途中失敗、OCR agentのheartbeat timeoutについて、旧本文・FTS・active publicationを同時に保持する
明示的な回帰testが不足していた。この3境界を追加し、公開transaction先頭で同一runを
`state='awaiting_qa'`条件付きno-op updateにより原子的にclaimして、同時再承認が二重publicationを
作らないことも固定する。追加監査で確認したSQLite Online Backupの未接続は、公開・rollbackの
書き込み予約後・canonical変更前に検証済み世代を原子的に作成し、参照をpublication履歴へ残す実装で解消した。
実backupの復元と`integrity_check`、backup例外時のcanonical無変更は自動testで固定した。
process hangについては親process側のstdout無通信期限、terminate、kill、generator破棄時回収を実装し、
実processを使う回帰試験と隔離server試験で孤児process 0を確認する。実ディスク不足と
本番filesystemでの世代公開は、mock DB例外だけで完了扱いにせず、隔離server運用試験を別途保存して
H5を完了する。

2026-08-23に実processがpage結果を1件返した後30秒sleepするケースを0.2秒無通信期限で実行し、
5秒以内の失敗化と子PID消滅を確認した。本番と同じext4配置先では388,210,688 bytesのOnline Backup、
原子的な世代公開、manifestと復元先の`integrity_check=ok`、canonical DBの前後SHA一致を確認し、
監査用世代は検証後に削除した。active production releaseには当該backup moduleがまだ含まれないため、
commit/deploy後のservice経路再確認を残す。実ENOSPCはhost filesystemを満杯にせず、Linux user namespace内の
8MiB tmpfsとsynthetic SQLiteで再現し、canonical SHA・`integrity_check`・未公開世代数を検査する。

同日の隔離実測は空き135,168 bytesでSQLite `OperationalError`を発生させ、canonical SHA不変、
`integrity_check=ok`、公開世代0件を確認した。namespace終了時にtmpfsは破棄され、host側の一時mountpointと
監査コードも削除した。commit/deploy後のactive release
`/opt/pic2pdf-viewer/backend-20260823102845-20977`から同じbackup moduleを実行し、本番ext4上で
388,210,688 bytesの世代公開、manifestと復元先の`integrity_check=ok`、canonical SHA不変を再確認した。
監査用世代だけを検証後に削除し、H5の障害注入・本番service経路確認を完了した。

## 9. 完了条件

B-35のレビュー前提laneは次の全条件を満たした時に完了とする。

- H1〜H5の受入条件が自動テストまたは保存済み監査成果物で検証される。
- Qwen＋dots複合engineの版・両raw候補・候補切替理由が保存され、1冊の全ページQAと全narrativeページの原画像照合を終えている。
- 必要な補正文を保存し、承認後公開と旧版rollbackを実行して本文・FTS・履歴の整合を確認する。
- QA未承認・品質未達・障害時に旧公開本文と索引が保持される。
- 自動公開またはCodex確認縮小は、正式holdoutでpolicy JSONの全項目が機械候補として合格するまで無効である。
- `docs/log/変更履歴.md` とB-35バックログを更新し、完了実績をarchiveへ移す。
