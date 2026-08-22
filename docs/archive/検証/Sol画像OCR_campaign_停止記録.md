# Sol画像OCR campaign実行計画

> frozen: 2026-08-22 | outcome: pilot不合格、全量展開停止
>
> 再開する場合も本記録をactive計画へ戻さず、固定manifestを更新した新計画を作成する。

> status: pilot-failed / full expansion stopped | started: 2026-08-19 | evaluated: 2026-08-19 | owner: main Sol session

medaroserverの正式小説画像をGPT-5.6 Solで再OCRし、既存OCRとの差を保存したうえで、
冊子単位に検証・正規昇格する。既存公開本文はlegacy版として残し、いつでもrollback可能にする。

## 固定対象

- 画像ディレクトリ: `/opt/pic2pdf-viewer/data/kindle_novel/images`
- 156冊、数値だけのstemを持つPNG 19,406画面
- 公開OCRあり: 81冊・9,911画面
- 画像のみ: 75冊・9,495画面
- `008_debug_vis.png` 2件など、stemが数字だけでない診断画像は対象外
- manifestはbook、page_no、相対path、画像SHA-256、size、冊子page数と全体digestを固定する

件数は2026-08-19の調査値である。実行の正本は生成後のcampaign manifestとし、
画像追加・変更があれば暗黙に取り込まず、新しいcampaignとして再固定する。

## 実行順序

1. 対象manifestを生成し、連番・復号・SHA・冊数・画面数を検査する。
2. SQLite Online Backupを取得・復元検証し、公開本文81冊を合成legacy runへsnapshotする。
3. standalone OCR worker importを修復し、診断PNG除外の回帰testを固定する。
4. Sol成果物schema、ページcheckpoint、比較report、publication切替とrollbackを実装する。
5. 画像のみ24画面、既存OCRあり57画面をpilotし、Sol raw、legacy差分、画像照合結果を保存する。
6. pilot合格後、最大3 workerへ冊子単位で重複なく分割して残りを処理する。
7. 冊子ごとに全page、画像SHA、空本文、反復、文字量外れ、先頭・中間・末尾標本を検査して昇格する。
8. 昇格後にFTSを同一transactionで更新し、全冊完了後にembedding等の派生成果物を再構築する。
9. 処理数、失敗・保留、legacy差分、verified標本のCER、利用上限停止回数を最終reportへ記録する。

## 並列・再開契約

- 1冊を1 workerだけが所有し、同じ冊子のページをworker間で分割しない。
- workerは固定manifestの割当分だけを読み、結果を1ページ1artifactとしてatomic保存する。
- 完了artifactは画像SHAとschemaが一致すれば再利用し、利用上限到達時は`paused_quota`で安全停止する。
- worker成果物からmedaroserverのSQLiteを直接更新しない。importはメインsessionが直列に行う。
- 同じpageの異なる有効結果が届いた場合は自動選択せず、競合として保留する。

## pilot合格条件

- manifest外画像、欠番、SHA変更、重複pageをfail closedで拒否する。
- 81画面すべてで構造化出力に成功し、ページ混同・列丸ごとの欠落・異常反復が0件である。
- 既存OCRあり57画面は差分を可視化し、差が品質改善か劣化かを原画像で判定する。
- legacy snapshot、Sol昇格、legacy rollbackをテストDBで往復し、本文・FTS・active履歴が一致する。
- pilot不合格時は全冊へ拡大せず、Sol runと成果物を保留状態で残す。

## 2026-08-19 実行結果

- campaign manifestは156冊・19,406画面で固定し、全画像の再hash照合に成功した。
  manifest SHA-256は`74eba62641115da405ad06b2f4d590249e7d30c67d450e662fc80708b9beeb88`。
- 実行前backupとpilot staging後backupを取得し、いずれも別ディレクトリへの復元検査に成功した。
- canonical 81冊・9,911正式画面を合成legacy runへsnapshotし、本文・page type・index対象を一致確認した。
  canonicalに残る診断画像由来2行はbackupへ保持し、versioned baselineからは除外した。
- pilot 81画面は3 workerで独立画像転記し、schema、sample ID、画像SHAを全件検証してSol stagingへimportした。
  canonical `pages`とactive publicationは変更していない。
- 既存本文あり57画面との正規化編集距離率は19.5696%だったが、legacyはverified ground truthではないため
  CERまたは精度として扱わない。本文比較可能な中間画面18件を原画像で独立判定した結果、
  Sol優位8件、legacy優位10件だった。
- legacy優位10件はすべて、本文列・台詞の欠落、読順破壊、固有名詞の系統誤認など重大なSol退行を含んだ。
  「列丸ごとの欠落0件」という合格条件に反するためpilotを不合格とし、全19,406画面への展開と正規昇格を停止した。
- Sol成果物81件、比較report、原画像判定3件はcampaign stagingへ残し、既存公開本文はlegacy activeのまま保持する。

再開には、同じ18画面とは別の未開封検証標本を固定し、欠落・読順・固有名詞退行を防ぐ方式を先に実証する。
今回のpilot結果を調整用データとして用いる場合、その18画面を次回の合否判定へ再利用しない。

## 再開プロトコル v2

1. 初回でlegacy優位だった10画面を`purpose=tuning`へ固定し、正式性能値から永久に除外する。
2. 同一画像を独立session A/Bが、右から左へ1〜2列重複する列帯ごとに転記する。
3. 第三sessionが原画像を左から右にも走査し、A/Bの列coverage、読順、台詞境界、固有名詞を検査する。
4. checkerが完全な候補を一意に選べない場合は`needs_review`とし、本文を合成・推測して補わない。
5. A/B/checkerのsession独立性、prompt/policy SHA、候補SHA、画像SHA、全sample集合を機械検証する。
6. tuning 10画面で重大欠落0を確認してprompt/policyを凍結する。改善値は正式性能として報告しない。
7. 初回pilot、B-35 formal holdout、その他開封済み標本をpage keyと画像SHAで除外し、品質非参照で
   fresh holdoutを選定・封印する。合格条件は開封前に固定し、ledgerを`opened`へ遷移してから
   SHA再検証付きで画像をexportし、一度だけ原画像判定する。
8. fresh holdoutでSol重大退行0、ページ混同0、列欠落0の場合だけ全冊処理へ進む。

初回失敗10件の非排他的分類は、本文欠落8件、読順・段落/発話構造崩れ6件、台詞/括弧境界5件、
固有名詞・専門語3件、意味を変える置換4件だった。したがって単純な全文再プロンプトではなく、
列coverageを成果物として証明することを再開条件とする。

## 2026-08-20 tuning結果

- 初回失敗10画面を独立候補A/Bと第三checkerで再処理し、5画面を`pass`、5画面を`needs_review`とした。
  checkerは不完全候補を採用せず、二次checkerも5画面すべてで「完全候補なし」と一致した。
- `needs_review` 5画面へ、原画像とcheckerの誤り分類だけを渡すbounded repair候補Cを実行した。
  3画面は独立画像checkerで`pass`したが、2画面は鉤括弧1組と二連ダッシュ1文字の欠落を検出して`fail`した。
- A/Bとbounded repairを合わせた確定可能数は8/10、未解決2/10、checkerの誤採用0件だった。
  開封済みtuning標本なので性能値には使用せず、重大誤差0の凍結条件を満たさないためfresh formal holdout、
  全19,406画面処理、canonical昇格は開始しない。
- 監査正本は`sol-ocr-rescue-tuning-result-v2`として候補・checkerのSHA、合否、停止判断を固定する。
  次の再開には、句読点・括弧・反復記号まで含む文字単位照合を独立checkerで機械強制できる新policyが必要。
- rescue監査一式はmedaroserverのcampaign領域へtarで退避し、archive SHA-256
  `1dac6e9736209ab568dcb8cb1b7b848c884c2248979f6aa054c6908e28e41557`、
  result SHA-256 `e8be9b9aa80dd30828939e953449984de75235ad7e8bc1f6d60fad86f6aad9c4`を照合した。
- `/opt/pic2pdf-viewer/backups/sol-rescue-closure`へ検証付きbackupを取得後、初回v1 staging 27 runを
  `failed/rejected`へ終了した。active publicationはlegacy 81冊、Sol 0冊、canonical `pages`は9,913行のまま。

## 2026-08-22 Google Document AI tuning結果

- 開封済みtuning標本から19冊30画面を固定し、Google Document AI Enterprise OCR
  `pretrained-ocr-v2.1.1-2025-01-31`を最大3並列で実行した。30/30画面でraw responseと本文を保存し、
  sample集合、画像SHA、response本文との対応を全件検証した。
- 既存本文あり21画面の既存OCRに対する空白除去編集距離率はGoogle 15.2420%、初回Sol 6.7566%だった。
  既存本文はverified ground truthではないため、CER・精度として扱わない。
- 独立画像checkerが採用可能とした参照のある8画面では、既存OCR 1.5180%、初回Sol 7.7799%、
  Google 19.8699%の差となり、8/8画面で既存OCRが最も近かった。参照自体も人手ground truthではなく、
  この比較を正式性能値へ含めない。
- Googleはルビ混入、縦列読順崩壊、見開き相当画像での断片移動、約物変形を示し、`pilot-059`では
  95.18%差の大規模読順崩壊が発生した。現versionの全冊展開とcanonical昇格を不採用とする。
- Google成果物はDBへimportせず、active publicationはlegacy 81冊、Sol 0冊を維持する。
  stable v1または`legacy_layout`の追加診断は別判断とし、実行する場合も開封済みtuning画面に限定する。

## 禁止事項

- B-35の開封済みformal holdoutを再評価・再調整に使わない。
- legacy差分率をCERまたは正解率として報告しない。
- 冊子の一部ページだけをcanonicalへ公開しない。
- 認証cache、API key、絶対path、DB接続情報をartifact・Git・ログへ含めない。
- backupとlegacy snapshotが検証できる前に既存公開本文を上書きしない。
