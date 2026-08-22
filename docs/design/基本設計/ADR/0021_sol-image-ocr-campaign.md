# ADR-0021: Sol画像OCRを版管理付きcampaignとして段階導入する

- **Status**: Accepted
- **Date**: 2026-08-19
- **決定者**: プロジェクトオーナー
- **関連**: [ADR-0018](0018_sol-primary-post-ocr-generation.md) / [OCR設計書](../../詳細設計/機能別/OCR設計書.md) / [Sol画像OCR campaign実行計画](../../../log/計画/Sol画像OCR_campaign実行計画.md)

## コンテキスト

medaroserverの正式小説画像を調査した結果、156冊・数値名PNG 19,406画面があり、
81冊・9,911画面には公開OCR本文、残る75冊・9,495画面には画像だけが存在した。
既存OCRとGPT-5.6 Solの画像読取り品質を同じ入力で比較し、Sol結果を新しい正規版として
利用したい。一方、現在の`pages`は上書き型で、公開前の本文を復元可能な版として保持しない。
またADR-0018はOCR承認済み本文の後処理だけを対象とし、原画像の送信を認めていない。

## 検討した選択肢

| 選択肢 | 判断 |
|---|---|
| 現行`pages`を直接上書き | 旧版を冊子単位で復元できないため不採用 |
| 既存approved runをlegacy版とみなす | 現在の公開本文と一致しない冊子があるため不採用 |
| 全ページを新しい版テーブルへ複製 | 明確だが既存run stagingと本文を二重管理するため初期導入では不採用 |
| canonical本文を合成legacy runへsnapshotし、公開履歴からactive runを切替 | 既存stagingを再利用でき、rollbackも同じ公開処理に集約できるため採用 |

## 決定

1. ユーザーが今回明示的に許可した156冊を、固定manifestに基づくSol画像OCR campaignとして扱う。
2. 原画像をGPT-5.6 Solへ送信する。対象はmanifest記載画像だけとし、APIキー課金へ自動切替しない。
3. 既存公開本文がある冊子は、Sol処理前にcanonical `pages`から`engine=legacy`の合成runを作る。
   既存runはlegacy正本として流用しない。
4. Sol結果は`ocr_runs` / `ocr_page_results`へページ単位でcheckpointし、冊子の全入力SHAと
   必須検査が揃った場合だけ正規版へ昇格できる。
5. active版は`ocr_publications`の追記型履歴で表す。昇格とrollbackは同じ冊子単位transactionで、
   旧activeのretire、`pages`、FTS、`books.ocr_done_at`、新active履歴を一括更新する。
6. 3 workerまで並列化するが、manifestを冊子単位で分割し、同じ冊子を複数workerへ割り当てない。
   workerはDBへ直接書き込まず、成果物をschema・画像SHA検証後にimportする。
7. 全冊実行前に、既存OCRなし24画面と既存OCRあり57画面のpilotを行う。完全性、可読性、
   legacy差分、失敗時rollbackを確認してから残りへ進む。
8. legacyとSolの文字差分率は品質正解率ではない。CERを名乗る比較は同一画像SHAの
   verified ground truthがある場合だけとし、既存B-35 formal holdoutを再利用しない。

## 結果

### ポジティブ

- Sol版を正規利用しつつ、旧公開本文を冊子単位で復元できる。
- 利用上限リセットを跨いでもmanifestとページcheckpointから再開できる。
- 画像だけの75冊も、既存OCRあり冊子と同じ公開契約へ載せられる。

### ネガティブ・受容したコスト

- 購入書籍の原画像がOpenAIへ送信される。モデル改善利用オフは運用前提でありアプリから検証できない。
- 19,406画面は単一の利用上限期間では完了しない可能性が高く、複数回の再開を前提とする。
- Sol自身による転記と確認は独立したground truthではないため、差分が小さいだけで正確とは断定しない。
- legacy snapshot、publication履歴、backup検証の追加運用が必要になる。

## 将来の再評価条件

- Responses Batch APIを使う明示許可とAPIキー課金方針が与えられた。
- 3 worker運用でも停止・再開コストが許容できない。
- pilotで重大な列欠落、ページ混同、反復、schema失敗が発生する。
- 外部送信を停止する必要が生じた、または保存期間・ZDR保証が必要になった。

## 実施結果（2026-08-19）

pilot 81画面の構造化転記とstaging importには成功したが、本文比較可能な中間画面18件の
原画像判定ではSol優位8件、legacy優位10件だった。legacy優位10件はすべて、本文列・台詞の欠落、
読順破壊、固有名詞の系統誤認など重大なSol退行を含んだ。この結果は決定7のpilot合格条件と
上記再評価条件に該当するため、全冊実行とSol版の正規昇格を停止した。

Sol runと比較・判定成果物はstagingへ保持し、canonical本文とactive publicationはlegacyのままとした。
同じpilotを調整後の正式合否判定へ再利用せず、再開時は未開封の別標本を固定する。

## 追加評価（2026-08-22）

開封済みtuning標本30画面をGoogle Document AI Enterprise OCR
`pretrained-ocr-v2.1.1-2025-01-31`でも処理した。30/30画面の成果物完全性は確認できたが、
独立画像checker採用候補がある8画面では既存OCRが8/8で最も参照に近く、Googleはルビ混入、
縦列読順崩壊、約物変形を示した。1画面では大規模な読順崩壊も発生した。

この標本は人手ground truthでもfresh formal holdoutでもないため、差分率をCER・正式精度とは扱わない。
Google結果はcanonicalへ公開せず、active publicationはlegacyのまま維持する。現versionを全冊へ拡大せず、
将来再評価する場合も別version・layout optionを開封済み調整用画面で先に診断し、独立検査とfresh holdoutを
通過した版だけを新しい候補として扱う。
