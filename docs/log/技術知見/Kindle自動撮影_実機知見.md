# Kindle 自動撮影 実機知見

> status: living | last-verified: 2026-08-22 | owner: Kindle capture

Kindle デスクトップアプリを使った連続撮影・取込について、現在再利用する実機上の確認手順と注意点をまとめる。
本書は契約を新設せず、要件と状態遷移は
[Kindle 自動撮影取込 要件](../../design/要件定義/Kindle自動撮影取込_要件.md)、実装契約は
[Kindle 購入カタログ設計](../../design/詳細設計/機能別/Kindle購入カタログ設計.md)を正本とする。
過去の受入結果と障害調査は[実機検証履歴](../../archive/検証/Kindle自動撮影_実機検証履歴.md)へ凍結した。

## 1. 実行前提

- Windows の Kindle デスクトップアプリへ対象 Amazon アカウントでログインしておく。
- Pic2PDFViewer backend と capture agent を起動し、購入カタログに対象 ASIN が存在することを確認する。
- Kindle、capture agent、シリーズ CLI を同一 Windows ユーザーで実行する。UI Automation セッションを跨がない。
- 画像、manifest、state、取込先の空き容量と書込権限を確認する。
- 同時に許可する active capture job は全 source・全 ASIN を通じて最大1件である。
- 既定は dry-run。実撮影は対象 manifest を確認してから `--apply` を明示する。

## 2. シリーズ連続処理

シリーズ CLI は inventory を取得し、指定順に1冊ずつ job を作成・監視する。state schema v2へ
manifest digest、完了 ASIN、撮影画面数、warning、復旧回数、停止理由を原子的に保存する。

- resume は `--resume-session` を明示し、同一 manifest・`running` state の場合だけ許可する。
- 完了 ASIN、画面数、warning の対応が崩れた state は resume しない。
- Kindle process の自動復旧は `--recover-kindle-crash` 指定時だけ有効で、撮影前または0画面、
  process 消失、許可 error code、同一 ASIN の一意照合、他 active job なしをすべて満たす場合に最大1回行う。
- `download_failed`を含む任意の1冊目の失敗でシリーズ全体を停止し、後続 job を作らない。
  失敗巻を隔離して継続する方式は将来候補であり、現行運用では使わない。
- 一時停止は新しい job を作成する前に行う。実行中 job を OS レベルで強制終了せず、状態とログを保全する。

## 3. Kindle UI 操作

- UI Automation の対象ウィンドウを一意に特定し、前面化とサイズ固定後に撮影する。
- 未ダウンロード書籍はダウンロード完了を待ち、タイムアウト時は `download_failed` として停止する。
- 先頭移動は直接移動を優先し、成立しない場合だけページ送りへフォールバックする。
- ページ送り後は描画安定を待ち、同一画面の連続取得、ページ不変、UI overlay を品質判定へ渡す。
- Kindle アプリ更新後はウィンドウタイトル、Automation 要素、本文矩形、移動操作を再検証する。

## 4. source 別の撮影範囲

| source | 基本単位 | 重要な確認 |
|---|---|---|
| `comic` | 見開き表示を含む画面 | 左右ページ順、中央綴じ、余白、ナビゲーションUI混入 |
| `novel` | 1画面 | 縦書き列の欠落、上下UI、通知overlay、小さい本文、ページ重複 |

本文矩形は固定値だけに依存せず、実機プロファイルと品質検査を組み合わせる。source を跨いで
画面数基準を共有しない。シリーズ画面数外れ値は同 source の成功済み3冊以上を母集団にした
warningであり、登録取消や後続停止には使わない。

## 5. 品質ゲート

登録前に package validator が manifest、画像列、hash、撮影枚数、warning policy を検査する。
不正型、欠落、重複、順序不整合、blocking overlay は fail closed とし、既存公開物を保持する。

目視確認では次を確認する。

1. 先頭・中間・末尾に欠落、重複、白紙化がない。
2. 漫画は見開き順と端切れ、小説は縦列・ルビ・上下端が成立する。
3. Kindle ナビゲーション、OS通知、カーソル等が本文へ重なっていない。
4. warning は候補ページと code を確認し、誤検知だけを承認する。

2026-08-22 の未調整524画面は人手確認で欠陥0件だった。これは陰性品質の受入であり、
実陽性検出率の証明には使わない。今後見つかった実障害は、修正前画像と確定 label を回帰コーパスへ追加する。

## 6. 公開・置換・キャッシュ

- 撮影成功だけでは公開完了としない。package 検証、転送、登録 transaction、公開先確認までを1単位とする。
- 置換時は既存画像を回復可能な形で退避し、途中失敗時は旧公開物と DB 参照を維持する。
- 公開後は API のページ数、先頭・末尾画像、reader の実表示を確認する。
- 同名画像を置換した場合、ブラウザーキャッシュで旧画像が見えることがある。再読込だけで判定せず、
  配信ファイルの hash と URL 応答を確認する。
- `novel` は画像公開後に OCR を別 job として実行し、OCR 品質ゲート合格前に本文・索引を置換しない。

## 7. 障害時の確認順

1. capture job の status、error code、heartbeat、撮影画面数を確認する。
2. Kindle process と対象 ASIN の表示状態を確認する。
3. session state と manifest digest を保全し、resume 条件を満たすか判定する。
4. download・UI不調・転送・登録失敗は自動復旧せず、原因解消後に新しい job として再実行する。
5. 既存公開物、索引、バックアップを確認してから再撮影・置換する。

## 8. 再検証トリガー

次の変更後は、漫画1冊・小説1冊以上で先頭から登録までを再確認する。

- Kindle アプリまたは Windows の更新
- UI Automation selector、本文矩形、ページ送り待機時間の変更
- capture agent、package validator、warning policy の変更
- 転送先、公開先、Samba、バックアップ経路の変更
- source 名または reader URL 契約の変更
