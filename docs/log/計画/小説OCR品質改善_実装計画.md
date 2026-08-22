# 小説OCR品質改善 実装計画

> 状態: 継続中 — B-35正式holdoutの機械強制は完了、機械単独品質が未達
> 更新日: 2026-08-22
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
作らないことも固定する。backup失敗・実ディスク不足と実process hangは、mock DB例外だけで完了扱いにせず、
隔離DBとserver運用試験を別途保存してH5を完了する。

## 9. 完了条件

B-35は次の全条件を満たした時だけ完了とする。

- H1〜H5の受入条件が自動テストまたは保存済み監査成果物で検証される。
- 正式holdoutでpolicy JSONの全項目が機械候補として合格する。
- QA未承認・品質未達・障害時に旧公開本文と索引が保持される。
- 自動公開またはCodex確認縮小の範囲、rollback条件、監査方法がOCR設計書と一致する。
- `docs/log/変更履歴.md` とB-35バックログを更新し、完了実績をarchiveへ移す。
