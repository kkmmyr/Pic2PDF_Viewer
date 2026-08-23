# ADR-0024: Qwen＋dots OCRをCodex管理の隔離実行・成果物反映に限定する

- **Status**: Accepted
- **Date**: 2026-08-23
- **決定者**: プロジェクトオーナー
- **Supersedes**: [ADR-0023](0023_risk-scoped-qwen-dots-review.md)の人手必須QAと本番engine切替方針
- **関連**: [OCR設計書](../../詳細設計/機能別/OCR設計書.md) / [小説OCR品質改善 実装計画](../../../log/計画/小説OCR品質改善_実装計画.md)

## コンテキスト

Qwen3.5-OCR-JP-2B＋dots.mocr複合版は、Apple Silicon 64GBの隔離pilotで、57画面の完走、
Codex原画像監査、4画面の補正、検証済みbackup、公開、旧版rollbackまで合格した。一方、機械signalだけでは
自然な誤認・文欠落・重複を完全に検出できず、ADR-0023はリスク対象の人手QAを公開条件としていた。
プロジェクトオーナーは日常運用で人手QAを原則行わない方針を選択した。

また、本番はLinux backend＋Windows OCR agent、複合workerはPyTorch MPS＋MLX-VLMを使うMac専用構成である。
Windows agentが取得する一時画像構造も複合workerの入力契約と一致しない。本番engineへ直接配線すると、
実行platform・model revision・入力配置の不一致を招く。

## 決定

1. `qwen35_dots_review_v1`をLinux本番またはWindows OCR agentへ配備せず、本番既定の
   `OCR_ENGINE=surya2`を維持する。
2. Qwen＋dotsはCodexがMac上の隔離DBで、1冊ずつ実行する。全冊一括実行と自動公開は行わない。
3. Codexは機械risk対象とclean標本を原画像で確認し、候補差分・既存canonical差分も監査する。
   原画像から確定できる箇所だけを補正し、辞書置換や推測補完を行わない。
4. プロジェクトオーナーの人手QAは通常フローから外す。原画像から一意に確定できない箇所、作品固有の表現、
   公開判断を変える重大な欠落疑いだけをfail closedで保留し、必要な場合に限って確認を依頼する。
5. 隔離成果は、書名、連続page集合、入力画像SHA-256、engine/model revision、両候補raw、選択理由、分類、
   Codex補正文、レビュー根拠、package digestを持つ版管理packageとしてexportする。
6. Linux側は本番画像からpage集合とSHA-256を再計算し、packageの完全性とdigestを検証してから
   `ocr_runs` / `ocr_page_results`へ冪等importする。Macから本番SQLiteを直接開かず、DB丸ごとの置換や
   手動SQL patchを行わない。
7. import後も即時公開しない。Codexが対象run、差分、未分類・未解決0件を再確認し、既存の検証済みbackupと
   原子的公開処理を明示実行する。異常時は旧active publicationを維持または再activateする。
8. reviewed packageのexport/importは`codex-reviewed-ocr-package-v1`として実装し、run 184の隔離DB往復で
   staging、明示公開、FTS同期、旧runへのrollbackを確認した。本番反映はCodexがこの経路を明示実行する場合に限る。

## 根拠

モデルruntimeを本番へ常駐させず、重い推論と画像レビューを検証済みMacへ限定することで、Linux/Windowsの
運用構成を壊さずに補正済み本文だけを利用できる。画像SHA、完全page集合、両候補raw、補正文、review根拠を
一体で封印し、Linux側で本番画像と再照合すれば、隔離DBのrun IDや絶対pathに依存せず監査可能に反映できる。

## 結果（Consequences）

- 日常的な人手QAは不要になるが、Codexレビューの見逃しリスクは残る。
- OCR実行はCodexセッションが必要で、無人の定期処理・自動全冊処理には使えない。
- runtime更新、model revision変更、prompt変更時は別package世代となり、過去のレビューを流用しない。
- 本番には推論runtimeを置かない一方、検証専用のreviewed package import機能を追加する必要がある。
- 曖昧な箇所を無理に公開せず、少数の利用者確認または旧本文維持へfail closedできる。

## 実装確認

2026-08-23にrun 184（57画面）をレビュー済みpackageへexportし、一時DBへ2回importした。初回は57件を
stagingし、2回目は同じrunへ57件すべてを冪等判定した。import前後のcanonical digestは
`76e65d4b9cf648edc6680a34f6ef212bd3041faebdaf0ce3e3563251e433c67d`で不変だった。明示公開後は
package本文・分類と57件すべて一致し、FTS不一致0件となった。旧run 76へrollback後は同じcanonical digestへ
復元し、publish／rollback前の2世代backupはmanifest SHA一致・`integrity_check=ok`、最終DBも
`integrity_check=ok`だった。本番DBは変更していない。

## 再評価条件

- 人手なしの未調整holdoutで機械gateを継続的に満たすOCRが得られた。
- Codexレビュー済み本文で、検索・要約の意味を変える見逃しが繰り返し発見された。
- 本番構成がApple Silicon workerを正式agentとして管理できる形へ変わった。
