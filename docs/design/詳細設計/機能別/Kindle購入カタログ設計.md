# Kindle 購入カタログ設計

> status: living | last-verified: 2026-07-31

## 1. 目的と境界

購入済み・借用・返品した Kindle 書籍を Linux サーバー上の Pic2PDF_Viewer で一元管理し、Amazon データの差分取り込み、検索、Pic2PDFViewer 内の画像との ASIN 紐付け、Windows キャプチャジョブの状態管理を画面から行う。

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

画面から作成した `capture_jobs` は Linux DB が正本となる。Windows エージェントは 1 件ずつ claim し、claim 応答の `identity`（ASIN、正式・正規化タイトル、著者、シリーズ、巻）を使って対象書籍を照合する。

状態遷移は `queued → claimed → locating_book → downloading（必要時）→ positioning → capturing → awaiting_files → succeeded` とし、各実行状態から `failed` へ遷移できる。既存 Windows エージェントとの段階導入互換性のため、`claimed → waiting_user → capturing` も読み書き可能な旧経路として維持する。

claim と状態更新時に `heartbeat_at` を更新し、agent は長時間工程中に heartbeat API を呼ぶ。次回 claim 時に、`KINDLE_CAPTURE_HEARTBEAT_TIMEOUT_SEC`（既定 300 秒）を超えた active job を `agent_heartbeat_timeout` で `failed` へ回収してから次の queued job を選ぶ。同一 agent が期限内に再 claim した場合は、現在の active job を返す。

成果物は Samba 上の論理専用受信箱へ `.partial` 名で送信し、完了後に
`.ready` へ rename する。既存環境では
`pic2pdf-input/.kindle-capture-inbox` を利用し、同人誌監視の対象から除外する。
Linux は `.ready` だけを検証し、安全な相対パス、許可拡張子、件数・容量上限を
確認してから正式配置する。

現行 Windows agent は自動工程を使用し、起動済み Kindle アプリへの接続、ASIN付きカードの一意照合、未ダウンロード待機、先頭移動、全画面撮影、Samba転送、正式登録までを 1 冊ずつ直列実行する。検索欄はIME依存のキーボード入力を使わず、UI Automationの`ValuePattern.SetValue`で半角ASINへ全置換し、読み戻し完全一致後だけASIN付きカードを探索する。旧 `waiting_user` は後方互換契約として残すが、現行 agent は使用しない。詳細は [Kindle 自動撮影取込 要件](../../要件定義/Kindle自動撮影取込_要件.md)と[完了記録](../../../archive/Kindle自動撮影取込_実装計画.md)を参照する。

撮影後・共有前に件数を検証し、`expected_screens`指定時は指定件数、未指定時は
小説50画面・漫画10画面を最低件数とする。未満なら`capture_incomplete`として
一時成果物を破棄し、既存の正式画像を置換しない。

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
- 購入書籍の詳細から対象、source、ページ送り方向、運用前提を確認して新規 job を作成する。同一 ASIN の active job または取込済み書籍では開始操作を無効化する。
- キャプチャページは active / failed / succeeded の工程、経過時間、撮影画面数、失敗別対処を表示し、failed job は確認ダイアログから新しい job として再実行する。
- 取込・管理は既存 3 API の順次実行と個別実行、最終結果、旧 DB 移行を集約する。
- 購入書籍の検索語、フィルター、ページ、ページ件数は URL クエリを正本とし、検索入力だけ 300ms のデバウンスを持つ。
- queryの許容値、既定25件、25/50/100件、正のpage検証、条件変更時のpage resetは
  `features/kindle/catalog-query.ts`を正本とする。URL更新は元の
  `URLSearchParams`を変更せず新しい値を返し、reloadと戻る・進むで同じ条件を復元する。
- iPad 相当幅では購入一覧の状態をタイトル下のバッジへまとめ、画像紐付けの 2 カラムを縦積みにする。端末種別による機能制限は行わない。

4ページへのUI再構成自体は既存 API、DB スキーマ、取込ロジックを変更していない。後続の自動撮影取込では capture job 状態、heartbeat、agent API を拡張したが、Amazonデータ取込、既存画像の自動ASIN確定、旧アプリ画像・表紙・レビュー移行は変更していない。
