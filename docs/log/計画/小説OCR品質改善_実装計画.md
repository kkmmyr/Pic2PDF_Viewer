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

## 7. Phase H4 — Codex確認縮小の段階評価

H3の機械総合合格後にだけ着手する。

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

B-35は次の全条件を満たした時だけ完了とする。

- H1〜H5の受入条件が自動テストまたは保存済み監査成果物で検証される。
- 正式holdoutでpolicy JSONの全項目が機械候補として合格する。
- QA未承認・品質未達・障害時に旧公開本文と索引が保持される。
- 自動公開またはCodex確認縮小の範囲、rollback条件、監査方法がOCR設計書と一致する。
- `docs/log/変更履歴.md` とB-35バックログを更新し、完了実績をarchiveへ移す。
