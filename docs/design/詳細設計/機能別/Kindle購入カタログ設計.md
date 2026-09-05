# Kindle 購入カタログ設計

> status: living | last-verified: 2026-09-05

## 1. 目的と境界

購入済み・借用・返品した Kindle 書籍を Linux サーバー上の Pic2PDF_Viewer で一元管理し、Amazon データの差分取り込み、検索、Pic2PDFViewer 内の画像との ASIN 紐付け、登録済み撮影品質warningの確認を画面から行う。

- 正本は Linux の `kindle_catalog.db` と `meta2.db`。
- Windows は Kindle アプリの操作と一時成果物の送信だけを担当する。
- `D:\61.tool\kindle購入履歴` の画像、表紙キャッシュ、`cover_local_path` は移行しない。
- Pic2PDFViewer の `comic` / `novel` 画像は削除・再コピーせず、ユーザー確認後に ASIN を `meta2.db` へ設定する。
- 感想、レビュー、評価、あらすじ、外部表紙取得は対象外。

## 2. データストア

[ADR-0016](../../基本設計/ADR/0016_kindle-catalog-sqlite.md)により専用SQLite DB、
[ADR-0017](../../基本設計/ADR/0017_kindle-catalog-runtime-sqlite3.md)により
schema管理と実行時accessの分離を採用する。

- 既定パス: `META_DB_DIR/kindle_catalog.db`
- 接続: WAL、foreign keys、busy timeout
- スキーマ管理: SQLModel定義と専用Alembic migration
- 実行時access: `services/kindle_catalog/connection.py`の短命`sqlite3`接続
- 一覧検索索引: タイトル正規化、取得日、種別、著者、シリーズ
- DB transaction 外で画像ファイルを直接更新しない

主要テーブルは `books`、`authors`、`book_authors`、`book_genres`、`purchases`、`borrowings`、`returns`、`series`、`book_series`、`series_subscriptions`、`imported_files`、`import_runs`、`capture_jobs` とする。

## 3. 初回移行

設定 `KINDLE_LEGACY_DB_PATH` が指す SQLite DB だけを read-only で開く。任意のリクエストパスは受け付けない。

1. preview で `PRAGMA integrity_check`、対応テーブル、件数、ASIN 欠損を確認する。
2. preview 結果に対する短期確認トークンを発行する。
3. commit は同じファイル fingerprint を再確認し、1 transaction で upsert する。
4. `book_reviews`、表紙パス、表紙キャッシュ、エンリッチ情報は読み込まない。
5. 移行元ディレクトリや画像ディレクトリは走査しない。

## 4. 継続取り込み

`AMAZON_DATA_DIR` 配下を、許可した正確なファイル名だけで再帰探索する。ファイルは SHA-256 と取り込み種別で冪等管理し、任意のリクエストパスは受け付けない。

medaroserver では `AMAZON_DATA_DIR=/opt/pic2pdf-viewer/import/kindle/files` を維持し、
同パスを `/opt/pic2pdf-viewer/data/doujin/input/.kindle-import` へのシンボリックリンク
とする。実ディレクトリは認証済みの既存 Samba 共有から
`\\medaroserver\pic2pdf-input\.kindle-import` として Windows に公開する。
先頭が `.` のため同人誌監視から除外され、Samba の `valid users = amashio` により
匿名アクセスを許可しない。ZIP はサーバー側で展開せず、Windows で展開した
許可対象 CSV / JSON だけを配置する。

- 注文、KU 借用、返品
- Kindle Info（書誌、ジャンル、著者、読書状態）
- シリーズ自動購入 JSON

<a id="kindle-amazon-export"></a>
### 4.1 Amazon エクスポートのバージョン選択

Amazon の Kindle エクスポートでは、従来の `_FE.csv` 名に代わり、同じ論理データが
`.1.1` / `.2.2` / `.3.1` などのバージョン付きファイルとして同梱される場合がある。
medaroserver へ配置する前に、列構成とデータ件数を確認し、書籍本体を含む完全な
バージョンを1つだけ選択して、バックエンドが認識する正規名へコピーする。
複数バージョンを結合・同時配置しない。

比較済みエクスポートの件数・採用元は
[追加実測履歴（凍結）](../../../archive/検証/Kindle購入カタログ_追加実測履歴_2026-09-05.md)を参照する。

バージョン番号だけを根拠に将来のファイルを自動採用しない。列構成、ASIN件数、
`Item Owner` の有無、旧版にしか存在しない有効ASINがないことを確認してから正規化する。

### 4.2 シリーズ自動購入データ

`kindle-series-autobuy.json` は今回の Kindle / Your Orders エクスポートには含まれない。
新しいエクスポートに存在しない場合は既存ファイルを維持する。
`Digital.SeriesContent.Relation.1/SeriesRelation.csv` はシリーズ関係データであり、
購読ID・購読状態を持たないため、自動購入 JSON の代替として使用しない。

Kindle Info はカタログに存在する ASIN だけを更新し、Info 側だけに存在する ASIN から書籍を新規作成しない。ジャンルは対象 ASIN 単位で置換し、著者・取得日・巻数は既存値を優先して補完する。シリーズ自動購入 JSON は Amazon 側で解除された購読を残さないよう、ファイル変更時に全量置換する。

注文、Kindle Info、自動購入の各取込は`import_run_lifecycle.py`を共通のrun履歴境界とする。
開始時に`running`行を作成し、成功時はfiles/records/skippedを同じcolumnへ確定する。
例外時は元の例外を再送出する前に`failed`、終了時刻、error messageを記録する。
各parserとupsertはrun lifecycleを直接更新せず、取込結果の件数だけを返す。
Kindle Infoのsource発見・CSV decode・digest・取込済み判定は`enrichment_files.py`、
既存ASINだけを対象とするsource別upsertは`kindle_info_importer.py`、自動購入のparse・
series解決・全量置換は`autobuy_importer.py`が所有する。`enrichment_imports.py`は既存API用facadeとする。

旧DB移行は通常の注文・Kindle Info・自動購入importerから参照しない。
設定有無の表示は軽量な`legacy_source_status.py`が担当し、破壊的なpreview/commit実装は
専用API呼び出し時だけ`legacy_migration.py`を遅延importする。撤去判断までは同moduleと
既存APIを読み取り可能に維持する。

パーサは未知列を無視し、注文系 CSV の必須列欠落時はファイル全体を失敗にする。カード番号や支払手段は保存しない。

## 5. 一覧・検索

`GET /api/kindle-catalog/books` はサーバー側ページングを行い、タイトル、ASIN、著者、種別、所有状態、画像取込状態で絞り込む。所有状態は購入・借用・返品履歴から、画像取込状態は `meta2.db.books_meta.asin` から導出する。

## 6. 既存画像の紐付け

未紐付け対象は Pic2PDFViewer の `comic` / `novel` に既に存在する書籍だけである。タイトル正規化・著者・シリーズ・巻数・種別から候補を返すが、自動確定しない。

PUT /api/kindle-catalog/links は `book_id` と ASIN を受け、対象がcomicまたはnovelであること、ASINがカタログに存在することを検証した後、既存フィールドを保持して`meta2.db.books_meta.asin`だけを更新する。

登録済み撮影のwarningは、登録成功と分離した「要確認候補」として書籍・code単位で件数と対象ページを表示する。候補ページを既存readerで開く操作は既読更新を行わず、既読・未確認の変更は明示操作だけで行う。章扉、表紙、挿絵、奥付等の正常例を含み得るため、warningを画像削除、OCR開始、自動停止へ流用しない。

<a id="kindle-capture-contract"></a>
<a id="7"></a>
<a id="7-キャプチャ連携"></a>
<a id="72-シリーズ直列実行"></a>
## 7. キャプチャ連携

capture状態、job identity、heartbeat、manifest、品質検査、シリーズ直列実行、停止・復旧の正本は
[Kindle自動撮影ジョブ契約](Kindle自動撮影ジョブ契約.md)とする。本書は購入データの取込、ASIN紐付け、
購入カタログ画面の表示を所有し、capture jobの実行契約を重複定義しない。

## 8. セキュリティ・障害時挙動

- Amazon 生データ、購入履歴、画像を外部サービスへ送信しない。
- Amazon データ入力ディレクトリの Samba アクセスは `amashio` に限定し、匿名アクセスを許可しない。
- API から任意絶対パスを指定できない。
- 注文番号と書籍タイトルを大量にログへ出さない。
- capture job の状態遷移は条件付き更新し、二重 claim を防ぐ。
- Kindle カタログの SQLModel は専用 metadata を使い、既存の小説 DB と同名の `books` テーブル定義を隔離する。
- カタログ DB はサーバーバックアップと週次復元試験へ含める。
- 不明な画像やレガシーアプリの画像を自動取り込みしない。

## 9. UI

通常運用UIは、購入書籍、画像紐付け、キャプチャ、取込・管理、価格監視の5ページで構成する。
`KindlePageShell`が共通サブナビゲーションを持ち、各ページは固有URLを持つ。
購入書籍を入口とし、価格監視の契約は[Kindle価格監視設計](Kindle価格監視設計.md)、
初期UIの要件と受入経緯は[凍結要件記録](../../../archive/要件/Kindle購入カタログ画面_UI改善_要件.md)を参照する。

フロントエンド実装は`features/kindle/`を所有境界とする。`api.ts`はHTTP、`queries.ts`は
TanStack Queryとinvalidate、`types.ts`はOpenAPI生成型alias、各`*Screen.tsx`は表示と
操作controllerを所有する。route pageはscreenを配置するだけとし、URL、query key、
invalidate範囲、toast文言、responsive layoutはfeature側が所有する。

- 購入書籍は検索中心の高密度テーブルとし、行から書籍詳細パネルを開く。
- 画像紐付けは Pic2PDFViewer の既存画像と Kindle カタログ候補を 2 カラムで比較し、最終確認後だけ ASIN を設定する。
- 購入書籍の詳細から対象、source、ページ送り方向、運用前提を確認して新規 job を作成する。
  capture job一覧のactive statusをASINで絞らず確認し、全source・全ASINのいずれかが未完了の間は
  開始操作を無効化する。同一ASINは従来の説明、他ASINは対象書籍またはASINと現在工程を表示し、
  どちらも既存jobのキャプチャ画面へ運ぶ。取込済み書籍も開始不可とする。
- pollingにより確認ダイアログ表示後にactive jobが判明した場合は確定ボタンも無効化し、
  handlerでもjob作成を行わない。backendの全体最大1件transaction制約は競合時の最終防衛線として維持する。
- キャプチャページは active / failed / succeeded の工程、経過時間、撮影画面数、失敗別対処を表示し、failed job は確認ダイアログから新しい job として再実行する。
- 同ページの要確認候補は`unread / read / all`を切り替え、未確認件数、code別説明、候補ページ、
  確認済み／未確認操作を表示する。ページ導線はnovelを`/novel/reader/:bookName?page=N`、
  comicを`/comic?file=:bookId&page=N`で開く。novelの`bookName`は保存用`book_id`末尾の`.pdf`を
  除いた画像ディレクトリ名とする。comic readerの`page`は初回表示だけに適用し、
  通常の別書籍選択ではURLから除去する。
- 取込・管理は既存 3 API の順次実行と個別実行、最終結果、旧 DB 移行を集約する。
- 購入書籍の検索語、フィルター、ページ、ページ件数は URL クエリを正本とし、検索入力だけ 300ms のデバウンスを持つ。
- queryの許容値、既定25件、25/50/100件、正のpage検証、条件変更時のpage resetは
  `features/kindle/catalog-query.ts`を正本とする。URL更新は元の
  `URLSearchParams`を変更せず新しい値を返し、reloadと戻る・進むで同じ条件を復元する。
- iPad 相当幅では購入一覧の著者をタイトル・ASINの下へ移し、種別・所有状態・画像状態をその下のバッジへまとめる。画像紐付けの 2 カラムは縦積みにし、端末種別による情報・機能の制限は行わない。

画面構成とAPI・DB契約を分けて管理する。capture jobの状態・heartbeat・agent APIは本書、
価格観測・通知はKindle価格監視設計を正本とし、画面の数からデータ更新範囲を推測しない。
