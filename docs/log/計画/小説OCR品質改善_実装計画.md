# 小説OCR品質改善 実装計画

> 状態: 継続中 — B-35正式holdoutの機械強制と機械単独品質が未達
> 更新日: 2026-08-10
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
| 正式holdoutの機械的封印 | 未完了 | シリーズ数、再開封台帳、全digestをCLIが強制しない |
| 機械単独・Codex省略 | 未完了 | 自動公開禁止を維持 |

## 4. Phase H1 — 正式holdoutをfail closed化する

### 実装

1. B-35用manifest schemaへ `series_id`、用途、固定日時、画像SHA、package digestを持たせる。
2. 選定時に3シリーズ以上、通常散文20画面以上、固有名詞10語・50出現以上を検査する。
3. 候補品質を参照せず選定したことを、選定入力と出力digestで再検証できるようにする。
4. holdout台帳へ `sealed` / `opened` / `retired_to_tuning` を記録し、`opened` の再評価を既定拒否する。
5. `seed`、`benchmark`、QA package生成・検証が同じmanifest schemaと全package digestを使う。
6. `--verify-queue` は優先部分だけでなく、選定全件のrun・page・画像SHA集合を検査する。
7. overrideは通常経路から分離し、理由・操作者・日時・旧新digestを監査JSONへ残す。

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
[リファクタリング契約表](リファクタリング契約表.md) を参照する。

## 9. 完了条件

B-35は次の全条件を満たした時だけ完了とする。

- H1〜H5の受入条件が自動テストまたは保存済み監査成果物で検証される。
- 正式holdoutでpolicy JSONの全項目が機械候補として合格する。
- QA未承認・品質未達・障害時に旧公開本文と索引が保持される。
- 自動公開またはCodex確認縮小の範囲、rollback条件、監査方法がOCR設計書と一致する。
- `docs/log/変更履歴.md` とB-35バックログを更新し、完了実績をarchiveへ移す。
