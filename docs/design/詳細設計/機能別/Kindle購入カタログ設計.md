# Kindle 購入カタログ設計

> status: living | last-verified: 2026-07-25

## 1. 目的と境界

購入済み・借用・返品した Kindle 書籍を Linux サーバー上の Pic2PDF_Viewer で一元管理し、Amazon データの差分取り込み、検索、Pic2PDFViewer 内の画像との ASIN 紐付け、Windows キャプチャジョブの状態管理を画面から行う。

- 正本は Linux の `kindle_catalog.db` と `meta2.db`。
- Windows は Kindle アプリの操作と一時成果物の送信だけを担当する。
- `D:\61.tool\kindle購入履歴` の画像、表紙キャッシュ、`cover_local_path` は移行しない。
- Pic2PDFViewer の `comic` / `novel` 画像は削除・再コピーせず、ユーザー確認後に ASIN を `meta2.db` へ設定する。
- 感想、レビュー、評価、あらすじ、外部表紙取得は対象外。

## 2. データストア

[ADR-0016](../../基本設計/ADR/0016_kindle-catalog-sqlite.md) により専用 SQLite DB を採用する。

- 既定パス: `META_DB_DIR/kindle_catalog.db`
- 接続: WAL、foreign keys、busy timeout
- スキーマ管理: SQLModel 定義と専用 migration
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

- 注文、KU 借用、返品
- Kindle Info（書誌、ジャンル、著者、読書状態）
- シリーズ自動購入 JSON

Kindle Info はカタログに存在する ASIN だけを更新し、Info 側だけに存在する ASIN から書籍を新規作成しない。ジャンルは対象 ASIN 単位で置換し、著者・取得日・巻数は既存値を優先して補完する。シリーズ自動購入 JSON は Amazon 側で解除された購読を残さないよう、ファイル変更時に全量置換する。

パーサは未知列を無視し、注文系 CSV の必須列欠落時はファイル全体を失敗にする。カード番号や支払手段は保存しない。

## 5. 一覧・検索

`GET /api/kindle-catalog/books` はサーバー側ページングを行い、タイトル、ASIN、著者、種別、所有状態、画像取込状態で絞り込む。所有状態は購入・借用・返品履歴から、画像取込状態は `meta2.db.books_meta.asin` から導出する。

## 6. 既存画像の紐付け

未紐付け対象は Pic2PDFViewer の `comic` / `novel` に既に存在する書籍だけである。タイトル正規化・著者・シリーズ・巻数・種別から候補を返すが、自動確定しない。

`PUT /api/kindle-catalog/links` は `book_id` と ASIN を受け、対象が `comic` または `novel` であること、ASIN がカタログに存在することを検証した後、既存フィールドを保持して `meta2.db.books_meta.asin` だけを更新する。

## 7. キャプチャ連携

画面から作成した `capture_jobs` は Linux DB が正本となる。Windows エージェントは 1 件ずつ claim し、ユーザーが Kindle アプリで対象書籍を開いたことを確認してから既存 capturer を起動する。

成果物は専用 Samba 受信箱へ `.partial` 名で送信し、完了後に `.ready` へ rename する。Linux は `.ready` だけを検証し、安全な相対パス、許可拡張子、件数・容量上限を確認してから正式配置する。

現在は対象書籍をユーザーが Kindle アプリで開く手動確認方式である。起動済み Kindle アプリへの接続、購入済みライブラリでの検索・本人照合、未ダウンロード待機、表紙・先頭移動を自動化する後続拡張は、[Kindle 自動撮影取込 要件](../../要件定義/Kindle自動撮影取込_要件.md)と[実装計画](../../../log/計画/Kindle自動撮影取込_実装計画.md)で管理する。実機成立性検証を通過するまでは、現行状態遷移と手動確認を変更しない。

## 8. セキュリティ・障害時挙動

- Amazon 生データ、購入履歴、画像を外部サービスへ送信しない。
- API から任意絶対パスを指定できない。
- 注文番号と書籍タイトルを大量にログへ出さない。
- capture job の状態遷移は条件付き更新し、二重 claim を防ぐ。
- Kindle カタログの SQLModel は専用 metadata を使い、既存の小説 DB と同名の `books` テーブル定義を隔離する。
- カタログ DB はサーバーバックアップと週次復元試験へ含める。
- 不明な画像やレガシーアプリの画像を自動取り込みしない。

## 9. UI

初回移行完了後の通常運用 UI は [Kindle 購入カタログ画面 UI/UX 改善 要件](../../要件定義/Kindle購入カタログ画面_UI改善_要件.md) に従い、購入書籍、画像紐付け、キャプチャ、取込・管理の 4 ページへ分離する。各ページは Kindle 領域内の共通サブナビゲーションと固有 URL を持ち、購入書籍を初期ページとする。

- 購入書籍は検索中心の高密度テーブルとし、行から書籍詳細パネルを開く。
- 画像紐付けは Pic2PDFViewer の既存画像と Kindle カタログ候補を 2 カラムで比較し、最終確認後だけ ASIN を設定する。
- キャプチャは運用設定完了まで利用準備中とし、新規ジョブ作成を表示せず既存ジョブだけ確認可能にする。
- 取込・管理は既存 3 API の順次実行と個別実行、最終結果、旧 DB 移行を集約する。
- 購入書籍の検索語、フィルター、ページ、ページ件数は URL クエリを正本とし、検索入力だけ 300ms のデバウンスを持つ。
- iPad 相当幅では購入一覧の状態をタイトル下のバッジへまとめ、画像紐付けの 2 カラムを縦積みにする。端末種別による機能制限は行わない。

本変更は UI-only とし、既存 API、DB スキーマ、取込ロジックを変更しない。
