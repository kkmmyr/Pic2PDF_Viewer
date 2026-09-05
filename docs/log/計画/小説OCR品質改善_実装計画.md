# 小説OCR品質改善 実装計画

> status: blocked | last-verified: 2026-09-05 | owner: project owner
>
> 状態詳細: H3は新しい独立候補の確定待ち、Mac比較は利用可能なMac環境とユーザー起点の再開待ち
> 対象: Kindle小説画像のOCR、品質判定、Windows OCR agent、QA公開

完了済み工程、候補比較、実測値、reviewed packageの公開・rollback記録は
[計画整理前全文（凍結）](../../archive/検証/小説OCR品質改善_計画整理前_2026-09-05.md)と
[OCR品質改善 技術知見](../技術知見/OCR品質改善_技術知見.md)を参照する。
現在の品質・公開契約は[OCR設計書](../../design/詳細設計/機能別/OCR設計書.md)、
判定値は`scripts/maintenance/ocr_quality_policy.json`を正本とする。

## 1. 目的

文字・縦列・入力範囲の欠落を見逃さず、品質確認後だけ`novel.db`と検索索引へ公開する。
処理完走、機械品質、画像照合QA、公開整合性を別の完了条件として扱う。

## 2. 維持する禁止事項

- QA未承認本文を`books` / `pages` / `pages_fts` / LanceDBへ公開しない。
- Windowsから本番SQLiteを直接更新しない。
- 原画像を見ないLLM補正や辞書置換を自動で正本にしない。
- キャプチャPNGを前処理・再試行・学習素材生成で上書きしない。
- 表紙・挿絵・奥付を理由に通常散文の閾値を緩和しない。
- 固定標本や開封済みholdoutの改善値を、未知標本への性能として報告しない。

## 3. 現在地

| 項目 | 状態 | 次の判断 |
|---|---|---|
| H3の未調整holdout | blocked | ページ最大CERを下げる新しい独立候補・仮説を先に固定する |
| reviewed packageによるCodex隔離運用 | 条件付き採用 | 原画像レビューと明示公開を省略せず、自動公開へ一般化しない |
| Mac補助OCRの製品比較 | blocked | 利用可能なMacとユーザーの再開指示が揃ってから無料体験を評価する |

H1・H2の完了工程と既存候補の不採用理由は、本文へ再掲せず凍結記録と技術知見を参照する。

## 4. Phase H3 — 未調整holdoutで機械候補を再評価する

ページ最大CERを下げる新しい独立候補または検出・部分再OCRの仮説を先に固定し、その候補だけを
新しい未調整holdoutで一度評価する。現行primary / external、NDLOCR-Lite、Qwen＋dots固定版など、
[OCR設計書の既知の制限](../../design/詳細設計/機能別/OCR設計書.md)にある既存候補を
同じ条件のまま再試行しない。候補の公開screening、model revision、prompt、seed、runtime manifestを固定し、
開封後の結果から候補選択規則を調整しない。

### 受入条件

policy JSONの全ゲートを同時に満たすこと。加重CERだけの合格、oracle、Codex補正文、
ground truth自身との比較を機械合格へ混ぜない。不合格なら同じholdoutで調整せず、
`retired_to_tuning`へ移して次の仮説を立てる。機械合格は自動公開を意味せず、OCR設計書のQA・
公開・rollback契約を別途満たす必要がある。

### 実施順序

1. 新候補の仮説、固定版、既存候補との独立性、失敗時の停止条件を承認する。
2. 品質を参照しない入力選定、画像SHA、reference SHA、package digestを検査してholdoutを封印する。
3. engine起動前にmanifest・policy digest・ページ種別・対象完全性を検証し、条件外ならfail closedで終了する。
4. 固定した候補を一度だけ実行し、項目別結果・終了コード・runtime manifestを保存する。
5. 合格時も画像照合QAと明示公開を省略せず、不合格時はholdoutを再利用しない。

<a id="mac-ocr-evaluation"></a>
## 5. Mac補助OCRの製品比較

MacはWindows主系とは独立した第二OCR・目視確認・比較評価手段として扱う。DB更新、正式公開、
入力来歴、比較時のruntime manifest、端末内処理の境界は
[Mac OCR補助確認設計](../../design/詳細設計/機能別/Mac_OCR補助確認設計.md)を正本とする。

### 候補と評価観点

| 候補 | 既存調査で挙げた評価観点（実施時に版・提供範囲を再確認） | 用途 |
|---|---|---|
| [OwlOCR](https://owlocr.com/) | Apple Vision OCRとローカルAI OCR、複数ページ、検索可能PDF、CLI、端末内処理 | ABBYYの結果が不十分な場合の追加候補。ページ単位テキスト出力と第二OCRの再現性を確認する |
| [ABBYY FineReader PDF for Mac](https://pdf.abbyy.com/ja/finereader-pdf-for-mac/) | 日本語を含むCJK、縦書き・横書き方向の指定、領域修正、文書変換 | 無料体験で縦書き本文の完全性と読み順を最初に確認する候補 |
| [Prizmo](https://creaceed.com/prizmo) | オンデバイス日本語OCR、画像補正、領域単位の再OCR、バッチ編集 | 歪み・傾き・低コントラスト等、入力画像の補正効果を評価する候補 |
| macOS Live Text / TextSniper | 画面上の範囲を即時OCR | QA中の部分照合専用。全冊処理や正式テキスト生成には使わない |

固定コーパスをページ対応が崩れずに完走し、アプリ版・設定・入力SHA-256・出力を追跡でき、
主系とは異なる誤りを原画像照合で発見できることを評価する。機密性と正式公開フローの条件も満たした
候補だけを補助手段として検討する。実施順序は次節に集約する。

### 購入・実施判断

評価はユーザーが利用できる時点に再開する。現時点では有償契約、買い切り購入、インストールを行わない。
まずABBYY FineReader PDFの無料体験範囲で固定20〜30画面を評価し、縦書き本文の完全性と読み順を確認してから、
1か月契約による1巻全体の評価要否を判断する。OwlOCR ProのローカルAI OCRとPrizmoは、ABBYYの結果が
不十分な場合の追加候補として保留する。評価中も本番DB、公開済みOCR、検索索引を更新しない。

### Mac / Windowsの同一条件比較

Mac版YomiTokuの比較は製品選定と分ける。同一画像SHA、同一YomiToku版、同一設定の
実行manifestを揃え、CPU / MPS / Windows側のdeviceを明記して本文一致率と速度を比較する。
通常PyTorch経路から始め、MPS非対応演算子のCPU fallbackを記録する。
Qwen＋dots＋Codexの合成runをMPS性能値へ流用しない。
未取得manifest、未記録時間は推測で埋めず、再測定が必要な項目として残す。

## 6. 機械総合合格後の追加確認

新しい未調整holdoutで全gateを満たすまでは、Codex原画像レビュー省略と自動公開を実装しない。
合格後にCodex確認縮小の反復・100画面試験へ進む場合も、subprocess、QA DB更新、FTS同期の
障害注入で旧公開状態が保持されることを確認する。既存基盤の完了履歴を、新候補の受入実績へ読み替えない。
