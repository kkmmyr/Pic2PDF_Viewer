# Kindle 購入カタログ統合 実装計画

作成日: 2026-07-25

状態: **実装完了（2026-07-25）**

現行契約: [Kindle購入カタログ設計](../design/詳細設計/機能別/Kindle購入カタログ設計.md)

UI 改善の後続作業: [Kindle 購入カタログ画面 UI/UX 改善 引継ぎ](Kindle購入カタログ画面_UI改善引継ぎ.md)

自動撮影の後続作業: [Kindle 自動撮影取込 実装計画](Kindle自動撮影取込_実装計画.md)

## 実装結果

- 実測 11,419 冊・単一利用者の条件に基づき専用 SQLite を採用し、PostgreSQL 移行条件を ADR-0016 に固定した。
- `/kindle/catalog` に検索・絞り込み、旧 DB 移行 preview/commit、3系統の差分取込、既存画像の確認付き紐付け、キャプチャジョブを集約した。
- Windows キャプチャエージェントと Linux inbox の `.partial` → `.ready` → 検証・正式配置を実装した。
- `kindle購入履歴` の画像・表紙キャッシュ・レビューは移行せず、既存画像は Pic2PDFViewer の `comic` / `novel` だけを対象とした。
- `kindle_catalog.db` を通常バックアップと復元検証へ追加した。

## 1. 目的

`D:\61.tool\kindle購入履歴` が持つ購入書籍カタログと Amazon データ取り込み機能のうち、Pic2PDF_Viewer の運用に必要な部分を本リポジトリへ移す。

購入書籍の確認、Amazon エクスポートの差分取り込み、既存画像との ASIN 紐付け、Kindle キャプチャ開始までを Pic2PDF_Viewer の画面から行えるようにする。

移行後の正本は Linux サーバー上の Pic2PDF_Viewer とし、`kindle購入履歴` アプリやその DB を通常運用時の依存先にしない。Windows PC は Kindle の画面取得だけを担当し、購入カタログ、ジョブ状態、画像の正式配置、メタデータ更新は Linux サーバー側で管理する。

## 2. 確定事項

| 項目 | 方針 |
|---|---|
| 正本の実行環境 | Linux サーバー（`medaroserver`） |
| 購入カタログの保存先 | Linux サーバー上の専用データストア。`meta2.db` とは論理的・物理的に分離する |
| DB 製品 | SQLite と PostgreSQL を Phase 0 で実測比較する。現時点の第一候補は SQLite、採用条件は §6.1 |
| 画像との接続キー | Amazon ASIN |
| 既存画像の識別子 | 従来どおり `meta2.db.books_meta` の `(source, book_id)` |
| カタログ上の画像取込状態 | `books_meta.asin` を読み、カタログ API の応答時に派生させる |
| 初回データ | 既存 `kindle購入履歴/app/data/kindle.db` から読み取り専用で一度だけ移行 |
| 移行元の画像 | `kindle購入履歴` 側の表紙・画像キャッシュ・画像パスは移行しない |
| 継続取り込み | Pic2PDF_Viewer が Amazon 注文 CSV / Kindle Info / 自動購入 JSON を直接差分取り込み |
| 画面 | `/kindle/catalog` に購入書籍、取込、既存画像紐付け、キャプチャジョブを集約 |
| キャプチャ実行 | Windows 専用キャプチャエージェントが Linux Web API のジョブを取得して実行 |
| キャプチャ成果物 | Windows のローカル一時領域から Linux の専用 Samba inbox へ転送し、Linux 側が検証後に正式配置 |
| 感想・レビュー | 移行・実装とも対象外 |
| 外部書誌 API | 初期スコープ外。Kindle/Amazon 由来データを優先する |
| 既存 Amazon CSV 機能 | 新機能の受入完了後に置換・撤去する |

## 3. スコープ

### 3.1 取り込む情報

- 書籍
  - ASIN
  - 正式タイトル
  - 著者
  - 出版社
  - ISBN / ISBN13
  - Kindle ジャンル（複数保持）
  - `comic` / `novel` / `other` 分類
  - Kindle 取得日
  - 累計読書時間
  - 最終読書日時
  - 読了状態
- 購入
  - 注文番号
  - 注文日
  - 注文状態
  - 数量
  - 額面、実支払額、値引、クーポン、税
- Kindle Unlimited
  - 借本日、返却日、状態
- 返品
  - 返品日、返金額、状態
- シリーズ
  - シリーズ名
  - 巻番号、巻ラベル
  - 手動修正保護情報
  - 続巻自動購入状態
- 取り込み管理
  - ファイル名
  - SHA-256
  - ファイル種別
  - 取込日時、処理件数、状態

### 3.2 画面から行える操作

- Amazon データの差分取り込み
- 未変更ファイルを含む強制再取り込み
- 初回レガシー DB 移行のプレビューと実行
- 購入書籍の検索・絞り込み・並べ替え
- 画像取込済み / 未取込の確認
- 既存 comic / novel 画像フォルダへの ASIN 紐付け
- 誤った紐付けの解除・再設定
- 購入書籍を指定したキャプチャジョブの作成
- キャプチャの進行状況と失敗理由の確認

### 3.3 対象外

- booklog 等のレビュー本文
- 感想の記録
- レビュースクレイピング
- `book_reviews` / `enrichment_candidates` / `series_extraction_log` の移行
- `kindle購入履歴/app/data/covers/` など移行元側の画像ファイル
- `cover_local_path` など移行元ローカル画像を指すパス
- NDL / Google Books / 楽天による自動書誌補完
- LLM によるシリーズ抽出・比較画面
- 購入金額ダッシュボード
- ほしい物リスト
- Amazon アカウントへのログイン自動化
- Kindle アプリ内で対象書籍を自動選択する操作
- ブラウザからの大容量キャプチャ画像アップロード
- Windows から Linux の正式画像ディレクトリへの直接書き込み

購入金額は元データとして保存するが、初期 UI は一覧・詳細表示までとし、高度な支出集計は別機能とする。

上記は A-4 初期統合時の対象外である。「Kindle アプリ内で対象書籍を自動選択する操作」は、初期統合完了後の独立機能 B-34 として要件を確定し、[Kindle 自動撮影取込 実装計画](Kindle自動撮影取込_実装計画.md)で管理する。

## 4. 現状ベースライン

2026-07-25 に読み取り専用で確認した値。

### 4.1 移行元

| 項目 | 件数 |
|---|---:|
| 書籍 | 11,419 |
| 購入 | 11,415 |
| KU 借本 | 254 |
| 返品 | 15 |
| シリーズ | 1,796 |
| シリーズ紐付け | 9,458 |
| 続巻自動購入 | 381 |
| comic 判定 | 10,704 |
| novel 判定 | 222 |

購入期間は 2014-06-01〜2026-04-26。件数は今後の追加取り込みで変わるため、実装テストでは固定値ではなく「移行プレビューと移行結果が一致すること」を判定する。

### 4.2 Pic2PDF_Viewer

| 項目 | 件数 |
|---|---:|
| comic 画像フォルダ | 27 |
| novel 画像フォルダ | 20 |
| `books_meta` の comic 行 | 0 |
| `books_meta` の novel 行 | 0 |

既存 47 冊と購入 DB の正規化タイトル完全一致は 2 冊だけであり、タイトル包含による自動確定は誤紐付けリスクが高い。既存分は候補提示 + 人による確認を必須とする。

ここでいう既存 47 冊は **Pic2PDF_Viewer 側の** `comic/images` / `kindle_novel/images` である。`kindle購入履歴` 側に保存された表紙・画像キャッシュは件数確認、コピー、候補生成、サムネイル流用のいずれにも使用しない。

## 5. アーキテクチャ

```text
Amazon Request My Data / 旧月別CSV / 自動購入JSON
                     │
                     ▼
   Linux: kindle_catalog import services
                     │  SHA-256・transaction
                     ▼
      catalog datastore (SQLite / PostgreSQL)
              │           │
              │ ASIN      │ capture_jobs
              ▼           ▼
          meta2.db      Web API
       books_meta.asin     │
              │            │ HTTPS
              │            ▼
              │      Windows capture agent
              │            │ SMB: *.partial → *.ready
              │            ▼
              │    Linux capture inbox
              │            │ 検証・安全な展開
              └──────◀─────┘
                 Linux正式画像領域
```

### 5.1 DB の責務

- 購入カタログデータストア
  - 「購入・取得した Kindle 書籍」の正本
  - Amazon データの再取り込みで更新される
  - 画像が存在しない書籍も保持する
- `meta2.db`
  - Pic2PDF_Viewer が実際に閲覧するローカル書籍のメタデータ
  - comic / novel の `book_id` と ASIN を結ぶ
- `novel.db`
  - OCR・全文検索・RAG の正本
  - 今回はスキーマ変更しない

カタログデータストアと `meta2.db` を SQL JOIN せず、サービス層で ASIN の集合を取得して応答を合成する。SQLite 採用時も通常の一覧要求で `ATTACH DATABASE` は使わない。PostgreSQL 採用時も `meta2.db` は移行せず、今回を他 DB の全面移行へ拡大しない。

### 5.2 Linux サーバー正本

次の処理はすべて Linux サーバー上の FastAPI / worker が担当する。

- カタログ DB の接続・migration・バックアップ
- Amazon 生データの検出と取り込み
- レガシー DB の初回移行
- カタログ検索・一覧・詳細 API
- キャプチャジョブの作成・状態管理
- Windows から届いた成果物の検証・安全な展開
- `meta2.db` への ASIN・書誌メタデータ反映
- 画像の正式公開とサムネイル生成

Amazon 生データは Linux の非公開領域へ同期してから取り込む。Windows の `D:\61.tool\kindle購入履歴` を通常運用時にネットワーク参照しない。

### 5.3 Windows キャプチャ境界

Kindle ウィンドウ、マウス、キーボードを操作できるのは Windows ホストだけである。FastAPI は Linux 上で動くため、Web API プロセスから `kindle-pdf` を直接起動しない。

Windows 側で `kindle-pdf/capture_agent.py` を起動し、次の流れで処理する。

1. Web 画面からキャプチャジョブを作成
2. エージェントが待機中ジョブを claim
3. 選択された書籍名・ASINを確認ダイアログに表示
4. ユーザーが Kindle アプリで対象書籍を開いたことを確認
5. 既存 capturer で画像取得
6. Windows ローカル一時フォルダで結果を検証
7. 画像と manifest をアーカイブし、Linux の Samba inbox へ `.partial` 名で転送
8. 転送完了後に同一ディレクトリ内で `.ready` へ rename
9. Linux worker が `.ready` を検出し、内容を再検証
10. Linux の一時展開先から正式画像フォルダへ atomic rename
11. バックエンドが `books_meta` へ ASIN・著者・シリーズ等を upsert
12. 完了 API / ジョブ状態へ結果を反映

Samba は既存 `pic2pdf-input` と分離した `pic2pdf-capture-inbox` 共有を追加する。共有先は Linux 側の専用 inbox だけに限定し、`comic/images` / `kindle_novel/images` の正式領域を Windows へ書き込み共有しない。

## 6. データモデル案

モデルは SQLModel、スキーマ変更は専用 Alembic 環境で管理する。接続 URL は `KINDLE_CATALOG_DATABASE_URL` から読み、SQLite / PostgreSQL のどちらを選んでもサービス・API・テストの契約を変えない。通常起動時に head まで upgrade し、`create_all()` をマイグレーション代替にしない。

### 6.1 SQLite / PostgreSQL の採否

現状の 11,419 冊・購入 11,415 件は SQLite にとって小規模であり、件数だけを理由に PostgreSQL を導入しない。Windows エージェントも DB へ直接接続せず Linux API を通るため、ネットワーク越し DB 接続も採用理由にならない。

一方で、Linux 常時稼働、複数キャプチャエージェント、取り込み中の画面操作、将来の複数ユーザー化まで見込む場合は PostgreSQL の行ロック・同時書き込み・運用監視が有利になる。Phase 0 で次の比較を実施し、ADR に結論を残す。

| 評価軸 | SQLite | PostgreSQL |
|---|---|---|
| 現在の件数 | 十分 | 十分 |
| 現在の単一ユーザー・低書込頻度 | 適合 | 過剰になりやすい |
| 既存運用との整合 | `meta2.db` / `novel.db` と同じバックアップ資産を再利用可能 | 新たに service、role、`pg_dump`、復元試験が必要 |
| 取り込み中の同時書き込み | WAL + 短い transaction で対応可能 | 行単位ロックで強い |
| 複数エージェントの job claim | 条件付き UPDATE で対応可能 | `FOR UPDATE SKIP LOCKED` が利用可能 |
| 将来の複数ユーザー化 | 制約が増える | 適合 |
| 障害調査・運用負荷 | 小 | 中 |

Phase 0 ベンチマーク:

- 現状データ相当
- 10 倍相当（約 12 万冊・購入 12 万件）
- 100 万購入行
- 1 取込 writer + 2 capture 状態 writer + 10 一覧 reader
- 一覧検索、シリーズ絞り込み、未取込判定、import upsert、job claim

SQLite 継続条件:

- 一覧 API の p95 が 300 ms 未満
- 取込中も一覧 API の p95 が 1 秒未満
- `database is locked` が 0 件
- job の二重 claim が 0 件
- 取込 transaction をファイル単位に分割しても運用時間内に完了

上記を満たす場合の推奨は SQLite とする。PostgreSQL を採用する条件は、SQLite が基準を満たさない、同時 writer が恒常的に 3 系統以上になる、複数ユーザー化を同時に実施する、または PostgreSQL の運用コストを許容してサーバー DB を統一する別計画が承認された場合とする。

SQLite 採用時:

- URL 既定値: `META_DB_DIR/kindle_catalog.db` から組み立てる SQLAlchemy SQLite URL
- WAL、foreign keys、busy timeout を有効化
- 既存 Online Backup API と週次復元試験へ追加

PostgreSQL 採用時:

- Linux ローカル PostgreSQL の専用 database / 非 superuser role を使用
- PostgreSQL ポートを LAN / Tailscale へ公開せず、FastAPI だけが接続
- URL と資格情報は権限を絞った systemd `EnvironmentFile` から読む
- 日次 `pg_dump --format=custom` と、別 temporary database への週次 restore test を追加
- SQLite 固有の `PRAGMA integrity_check` は PostgreSQL の dump / restore 検証へ置換

### 6.2 主要テーブル

| テーブル | 主キー / 一意制約 | 用途 |
|---|---|---|
| `books` | `asin` | 書籍マスタ |
| `authors` | `id`、`name_key` unique | 著者名の正規化 |
| `book_authors` | `(asin, author_id)` | 複数著者と表示順 |
| `book_genres` | `(asin, genre)` | Kindle ジャンルを複数保持 |
| `purchases` | `(order_number, asin, title)` unique | 購入履歴 |
| `borrowings` | `(asin, loan_creation_date)` unique | KU 借本履歴 |
| `returns` | `(asin, order_id, return_date)` unique | 返品履歴 |
| `series` | `id`、`(name, author_key)` unique | シリーズ |
| `book_series` | `asin` unique | 書籍とシリーズ・巻番号 |
| `series_subscriptions` | `series_asin` | 続巻自動購入 |
| `imported_files` | `(source_kind, filename, sha256)` unique | 差分取込 |
| `import_runs` | `id` | UI に表示する取込単位の状態・集計 |
| `capture_jobs` | `id` | Web と Windows エージェント間のジョブ |

### 6.3 `books`

最低限、次のカラムを持つ。

- `asin: str` — 主キー
- `title: str`
- `title_normalized: str`
- `publisher: str | null`
- `isbn: str | null`
- `isbn13: str | null`
- `category: str`
- `book_type: comic | novel | other | unknown`
- `kindle_acquisition_date: datetime | null`
- `total_reading_ms: int | null`
- `last_read_at: datetime | null`
- `is_completed: bool | null`
- `created_at`, `updated_at`

レビュー、評価、あらすじ、表紙キャッシュ、外部 API の取得状態は持たない。

### 6.4 `capture_jobs`

| カラム | 内容 |
|---|---|
| `id` | UUID |
| `asin` | 対象書籍 |
| `source` | `comic` / `novel` |
| `status` | `queued` / `claimed` / `waiting_user` / `capturing` / `awaiting_files` / `succeeded` / `failed` / `cancelled` |
| `direction` | `left` / `right` |
| `expected_screens` | 任意。Kindle 紙面ページ数ではない |
| `requested_at` / `claimed_at` / `started_at` / `completed_at` | 状態時刻 |
| `agent_id` | claim した Windows エージェント |
| `book_id` | 保存後の `books_meta.book_id` |
| `captured_screens` | 保存画像数 |
| `error_code` / `error_message` | 失敗理由 |

1 エージェントが同時に claim できる実行中ジョブは 1 件までとし、transaction 内の条件付き UPDATE で二重 claim を防ぐ。

### 6.5 所有・画像取込状態

次の値は重複保存せず、API 応答時に導出する。

- `ownership`
  - `purchased`
  - `borrowed_active`
  - `borrowed_ended`
  - `returned`
- `capture_state`
  - `not_captured`
  - `captured`
  - `multiple_links`
  - `capture_pending`

`captured` は `meta2.db.books_meta.asin` に同じ ASIN があることを条件とする。複数行に同じ ASIN がある場合は自動的に片方を消さず、`multiple_links` として UI で確認させる。

## 7. 取り込み設計

### 7.1 入力ルート

Linux サーバーの `AMAZON_DATA_DIR` を再利用し、次の構成を参照する。推奨値は `/opt/pic2pdf-viewer/import/kindle` とし、Web 静的配信領域および Samba 公開領域の外へ置く。

```text
AMAZON_DATA_DIR/
├── amazon-order/
│   └── Your Amazon Orders/
├── amazon-order_digital/
├── kindle-info/
└── json/
```

HTTP リクエストから任意の絶対パスを受け取らない。画面は設定済みルートの状態と検出ファイルだけを表示する。

Amazon の新しいエクスポートは Windows で展開後、管理用同期スクリプトで Linux の `AMAZON_DATA_DIR` へ転送する。画面から Windows ローカルパスを参照しない。

初回移行元 DB も Linux へコピーし、任意リクエストパスではなく設定 `KINDLE_LEGACY_DB_PATH` から解決する。未設定時は移行 UI を無効化する。

### 7.2 対応ファイル

優先度順:

1. `Digital Content Orders.csv`
2. `Digital Borrowed Items.csv`
3. `Digital Returns.csv`
4. `CustomerRelationshipIndex_FE.csv`
5. `CustomerGenres_FE.csv`
6. `CustomerAuthorNameRelationship_FE.csv`
7. `CollectionRightsDatastore.csv`
8. `reading-insights-sessions_with_adjustments.csv`
9. `whispersync.csv`
10. `Kindle.Devices.autoMarkAsRead.csv`
11. `kindle-series-autobuy.json`
12. `amazon-order_digital/*.csv`（旧形式互換）

### 7.3 共通規則

- UTF-8 / UTF-8-SIG / CP932 を判定する
- ファイル全体の SHA-256 で未変更ファイルをスキップする
- パーサと DB 書き込みを分離する
- 1 ファイル単位で transaction を張る
- パース失敗時はそのファイルを失敗にし、途中行を確定しない
- 再取り込みは upsert と unique 制約で冪等にする
- 未知カラムは無視し、必須カラム欠落は明示エラーにする
- カード番号・支払手段は取り込まない
- ログへ注文番号・書籍タイトルを大量出力しない
- 既存の手動シリーズ修正は自動処理で上書きしない

### 7.4 初回レガシー DB 移行

移行は preview と commit の 2 段階にする。

Preview:

- 移行元 SQLite DB の `PRAGMA integrity_check`
- 対応スキーマか確認
- 対象テーブルの件数集計
- 移行対象 / 除外対象の表示
- ASIN、シリーズ、著者の重複・欠損集計
- commit 用の短期確認トークン発行

Commit:

- 移行元を read-only URI で開く
- 選定したカタログデータストアの事前バックアップ
- transaction 内で upsert
- preview 件数との一致確認
- SQLite は `PRAGMA integrity_check`、PostgreSQL は dump / temporary restore で検証
- 移行結果を `import_runs` に保存

移行しないテーブル:

- `book_reviews`
- `enrichment_candidates`
- `series_extraction_log`
- `reading_day_stats`

`books` からもレビュー評価、あらすじ、`cover_local_path`、外部表紙、外部エンリッチ状態は除外する。移行処理は移行元 DB 以外のファイルを走査・コピーせず、Pic2PDF_Viewer 側の既存画像だけを後続 Phase 4 の紐付け対象とする。

## 8. API 設計案

全エンドポイントに具体的な `response_model` を設定し、OpenAPI 生成型をフロントエンドから参照する。

### 8.1 カタログ

| Method | Path | 用途 |
|---|---|---|
| GET | `/api/kindle-catalog/books` | 検索、ページング、絞り込み |
| GET | `/api/kindle-catalog/books/{asin}` | 書籍詳細 |
| GET | `/api/kindle-catalog/series` | シリーズ一覧 |
| GET | `/api/kindle-catalog/series/{series_id}` | シリーズ詳細 |
| GET | `/api/kindle-catalog/stats` | 件数・取込状態サマリ |

一覧フィルタ:

- `q`
- `book_type`
- `ownership`
- `capture_state`
- `completed`
- `series_id`
- `author`
- `order_from` / `order_to`
- `sort` / `order`
- `page` / `page_size`

### 8.2 取り込み

| Method | Path | 用途 |
|---|---|---|
| GET | `/api/kindle-catalog/imports/sources` | 設定・検出ファイル・最終取込の確認 |
| POST | `/api/kindle-catalog/imports/orders` | 注文/KU/返品の差分取込 |
| POST | `/api/kindle-catalog/imports/kindle-info` | Kindle Info 差分取込 |
| POST | `/api/kindle-catalog/imports/autobuy` | 自動購入 JSON 取込 |
| GET | `/api/kindle-catalog/imports/runs` | 取込履歴 |
| GET | `/api/kindle-catalog/imports/runs/{run_id}` | 取込結果詳細 |
| POST | `/api/kindle-catalog/migration/preview` | 既存 DB 移行プレビュー |
| POST | `/api/kindle-catalog/migration/commit` | 確認トークン付き移行 |

長時間処理は API リクエスト内で完走させず、ジョブとして実行する。画面は TanStack Query で状態をポーリングする。

### 8.3 既存画像の紐付け

| Method | Path | 用途 |
|---|---|---|
| GET | `/api/kindle-catalog/links/unlinked` | ASIN 未設定の comic / novel 一覧 |
| GET | `/api/kindle-catalog/links/candidates` | 対象 `book_id` の候補 |
| PUT | `/api/kindle-catalog/links` | ユーザー確認済み ASIN を設定 |
| DELETE | `/api/kindle-catalog/links` | ASIN 紐付け解除 |

候補スコアは次の要素を使う。

- book_type と source の一致
- 正規化タイトル完全一致
- シリーズ名
- 巻番号
- 著者
- 既存 ASIN

候補が 1 件でも、人の確定操作なしに `books_meta.asin` を更新しない。

### 8.4 キャプチャジョブ

Web UI:

| Method | Path | 用途 |
|---|---|---|
| POST | `/api/kindle-catalog/capture-jobs` | ジョブ作成 |
| GET | `/api/kindle-catalog/capture-jobs` | 一覧 |
| GET | `/api/kindle-catalog/capture-jobs/{job_id}` | 状態 |
| POST | `/api/kindle-catalog/capture-jobs/{job_id}/cancel` | 待機中/実行中の取消要求 |

Windows エージェント:

| Method | Path | 用途 |
|---|---|---|
| POST | `/api/kindle-catalog/agents/claim` | 次の待機ジョブを排他的に取得 |
| POST | `/api/kindle-catalog/agents/jobs/{job_id}/state` | 進捗更新 |
| POST | `/api/kindle-catalog/agents/jobs/{job_id}/complete` | 完了報告 |
| POST | `/api/kindle-catalog/agents/jobs/{job_id}/fail` | 失敗報告 |

エージェント API は `Authorization: Bearer` の専用トークンを要求する。トークンは DB やログに平文保存せず、環境設定から読む。

## 9. フロントエンド設計案

### 9.1 ナビゲーション

ヘッダーに「Kindle > 購入書籍」を追加し、`/kindle/catalog` へ遷移する。

### 9.2 ページ構成

`KindleCatalogPage` に次のタブを設ける。

1. **購入書籍**
   - 検索
   - comic / novel / other
   - 購入 / KU / 返品
   - 画像取込済み / 未取込
   - 読了状態
   - シリーズ
   - ページング
2. **データ取込**
   - 入力ルート設定状態
   - 検出ファイル
   - 差分取込 / 強制再取込
   - 既存 DB 初回移行
   - 取込履歴
3. **既存画像の紐付け**
   - ASIN 未設定の comic / novel
   - 購入カタログ候補
   - 手動検索
   - 確定 / 解除
4. **キャプチャ**
   - 待機・実行中・完了・失敗ジョブ
   - エージェント接続状態
   - 失敗理由

### 9.3 書籍詳細

- 基本書誌
- 購入・KU・返品履歴
- シリーズと巻番号
- Kindle 取得日・読書状態
- 現在紐付いている画像
- 「漫画としてキャプチャ」「小説としてキャプチャ」

「キャプチャ開始」は即座にマウス操作を始めず、確認ダイアログで次を表示する。

- 対象タイトル
- ASIN
- comic / novel
- ページ送り方向
- 任意の期待撮影画面数
- 「Kindle アプリでこの書籍を開いてください」という確認

## 10. キャプチャ結果の契約

エージェントは Windows ローカル一時フォルダへ次の manifest を保存し、画像とともに 1 ジョブ 1 アーカイブへ格納する。

`.pic2pdf-capture.json`

```json
{
  "format_version": 1,
  "job_id": "uuid",
  "asin": "B0...",
  "source": "novel",
  "book_id": "表示用タイトル",
  "captured_screens": 97,
  "completed_at": "2026-07-25T12:34:56+09:00"
}
```

転送契約:

- Windows 転送中: `<job_id>.zip.partial`
- Windows 転送完了: `<job_id>.zip.ready`
- Linux inbox: `/opt/pic2pdf-viewer/data/kindle_capture_inbox/`
- Linux 展開中: 正式画像領域外の同一 filesystem 上にある一時ディレクトリ
- Linux 公開時: `get_dirs_by_source(source)["img"]/<book_id>/` へ atomic rename

Linux worker はアーカイブを安全に展開し、manifest と実ファイルを照合する。

- ASIN、source、job_id が一致
- 画像が 1 件以上存在
- 画像連番に重複がない
- 許可拡張子以外が含まれない
- 絶対パス、`..`、symlink、展開先外への escape がない
- ファイル数・展開後総サイズが設定上限以内
- Linux 正式フォルダへの公開後に全画像が存在する

確認・正式公開後、manifest も正式フォルダへ保存し、`books_meta` に次を補完する。

- `asin`
- `authors`
- `publisher`
- `isbn`
- `genre`
- `series_id`
- `series_title`
- `series_index` または `volume`

既存値は原則保持する。シリーズ等で既存値とカタログ値が衝突した場合は自動上書きせず、ジョブ結果に警告を残す。

## 11. 実装 Phase

### Phase 0 — 設計正本とテスト資材

作業:

- 要件定義へ購入カタログ要件を追加
- 基本設計へ Linux 正本、DB 分離、Windows エージェント境界を追加
- 詳細設計、API、セキュリティ設計を更新
- SQLite / PostgreSQL の比較ベンチマークを実装・実行
- DB 採否を ADR として確定
- Linux の import root / capture inbox / backup / systemd 構成を確定
- 移行元から個人情報を除いた最小 CSV / JSON / SQLite fixture を作成
- 現状件数を移行検証用レポートとして保存

完了条件:

- 設計書間で DB、ASIN、キャプチャジョブの正本が一致
- SQLite / PostgreSQL の比較結果と採否理由が ADR に残っている
- Linux 以外にカタログ DB の正本を置く経路がない
- fixture に実注文番号、カード情報、私的タイトルが含まれない
- `check-docs` が通る

### Phase 1 — カタログ DB とレガシー移行

作業:

- SQLModel モデル
- 専用 Alembic 環境
- 接続・transaction・read facade
- 起動時 migration
- レガシー移行 preview / commit
- Linux への Amazon 生データ・レガシー DB 同期スクリプト
- 選定 DB に応じた日次バックアップ・週次復元試験
- PostgreSQL 採用時は package / role / database / systemd 環境設定を構成

完了条件:

- 移行元 DB を更新しない
- `kindle購入履歴` 側の画像ディレクトリを読み取り・コピーしない
- preview と commit の対象件数が一致
- 対象データの再実行が冪等
- 除外テーブル・除外フィールドが作成されない
- SQLite は移行後 `PRAGMA integrity_check` が `ok`
- PostgreSQL は custom dump から temporary database への restore test が成功
- DB ポートを LAN / Tailscale へ公開していない

ロールバック:

- SQLite は移行前バックアップへ戻すか、新規 `kindle_catalog.db` だけを退避して再作成
- PostgreSQL は移行前 custom dump を新規 database へ restore して接続先を戻す
- `meta2.db` / `novel.db` は変更しない

### Phase 2 — Amazon データ差分取り込み

作業:

- 共通文字コード判定
- ファイル形式ディスパッチ
- 注文/KU/返品パーサ
- Kindle Info パーサ
- 自動購入 JSON パーサ
- 旧月別 CSV 互換
- SHA-256 差分管理
- 取込ジョブと進捗 API

完了条件:

- 同じ入力を 2 回処理して件数が増えない
- 変更ファイルだけが再処理される
- 不正ファイルが正常ファイルの確定を壊さない
- カード情報を保存しない
- 既存手動シリーズ修正を上書きしない

### Phase 3 — 購入カタログ画面

作業:

- カタログ API
- `/kindle/catalog`
- ナビゲーション
- 購入書籍 / データ取込タブ
- 書籍詳細
- URL クエリ同期
- OpenAPI 型再生成

完了条件:

- 11,000 冊規模でサーバー側ページングされる
- 検索・book_type・ownership・capture_state が組み合わせ可能
- ブラウザ戻る操作でフィルタが復元される
- 取込の成功・スキップ・失敗が画面で区別できる

### Phase 4 — 既存画像 47 冊の ASIN 紐付け

作業:

- 未紐付け一覧
- 候補スコアリング
- 候補確認 UI
- 手動検索
- 確定 / 解除 API
- `books_meta` 部分更新

完了条件:

- 候補取得だけでは DB を変更しない
- 確定後、カタログ一覧が画像取込済みに変わる
- 解除後、元のメタデータを消さず ASIN だけを解除できる
- 47 冊すべてが「紐付け済み」または「意図的に未紐付け」に分類される

### Phase 5 — Windows キャプチャエージェント

作業:

- `capture_jobs`
- エージェント認証・claim API
- `capture_agent.py`
- capturer の CLI 引数対応
- 既存ダイアログへのカタログ情報表示
- Windows ローカル一時フォルダと manifest
- Linux `pic2pdf-capture-inbox` Samba 共有
- `.partial` → `.ready` 転送プロトコル
- Linux 側の安全な ZIP 展開・検証 worker
- Linux 一時領域から正式画像領域への atomic rename
- 完了時 `books_meta` upsert
- キャプチャ画面

完了条件:

- Web で指定した ASIN が manifest と `books_meta` に一致する
- 同時に 2 台が同じジョブを claim できない
- Windows はカタログ DB / `meta2.db` / Linux 正式画像領域へ直接書き込まない
- キャプチャ・転送・展開の失敗時は正式フォルダと `books_meta` を作らない
- キャンセル時に中間画像を正式ライブラリへ混入させない
- 悪意ある ZIP パス、symlink、上限超過を拒否する
- comic / novel を各 1 冊ずつ実機スモークテストする

### Phase 6 — 切替と旧機能撤去

作業:

- 旧 `AmazonImportButton` を新画面へのリンクへ置換後、撤去
- 旧 `routers/amazon_import.py`
- 旧 `services/amazon_csv_importer.py`
- 旧 `services/amazon_csv_parser.py`
- 不要になったテスト・API 定義を削除
- 設計書・ファイルマップ・変更履歴を最終同期

完了条件:

- `/api/amazon/import` の利用箇所がない
- 新カタログから同等以上の authors / ASIN 補完が可能
- lint、型チェック、backend/frontend テスト、production build、docs check が通る

## 12. 影響ファイル案

### 12.1 バックエンド

新規:

```text
backend/
├── alembic_catalog/
├── alembic_catalog.ini
├── routers/kindle_catalog/
│   ├── books.py
│   ├── imports.py
│   ├── links.py
│   ├── capture_jobs.py
│   └── schemas.py
└── services/kindle_catalog/
    ├── connection.py
    ├── models.py
    ├── migrations.py
    ├── repository.py
    ├── import_runner.py
    ├── legacy_migration.py
    ├── link_candidates.py
    ├── capture_jobs.py
    ├── capture_ingest.py
    ├── storage_benchmark.py
    └── importers/
        ├── encoding.py
        ├── orders.py
        ├── borrowings.py
        ├── returns.py
        ├── kindle_info.py
        ├── autobuy.py
        └── legacy_monthly.py
```

変更:

- `backend/config/__init__.py`
- `backend/main.py`
- `backend/services/meta_store.py`
- `backend/services/meta_db_backup.py`
- `backend/tools/server_backup.py`
- `backend/routers/api_schemas.py`（新 router 内へ閉じられない共通型のみ）
- `deploy/backup-meta.service`
- `deploy/backup-restore-test.service`

PostgreSQL 採用時に追加:

- PostgreSQL 初期設定スクリプト
- `pg_dump` 日次 backup 用 systemd service / timer
- temporary database restore test 用 systemd service / timer
- Python PostgreSQL driver

### 12.2 フロントエンド

```text
frontend/src/
├── features/kindle_catalog/
│   ├── api.ts
│   ├── queryKeys.ts
│   ├── types.ts
│   └── components/
├── hooks/kindle_catalog/
└── pages/KindleCatalogPage.tsx
```

変更:

- `frontend/src/router.tsx`
- `frontend/src/lazyPages.tsx`
- `frontend/src/components/Layout.tsx`
- `frontend/src/config/api.ts`
- `frontend/src/types/api.d.ts`

### 12.3 キャプチャ

- `kindle-pdf/capture_agent.py`（新規）
- `kindle-pdf/capturer.py`
- `kindle-pdf/novel_capturer.py`
- `kindle-pdf/main_auto.py`
- `kindle-pdf/main_novel.py`
- `kindle-pdf/run_capture_agent.bat`（新規）
- `scripts/sync_kindle_catalog_inputs.sh`（Windows/管理PC → Linux import root）
- `docs/design/環境構築/Linux_Sambaセットアップ.md`

## 13. テスト計画

### 13.1 バックエンド単体

- 全パーサの正常・欠損列・文字コード
- Component 行集約
- 金額・日付・boolean 変換
- タイトル・著者・ジャンル正規化
- book_type 分類
- SHA-256 スキップ
- unique 制約と upsert
- 手動シリーズ保護
- 候補スコアリング
- capture job 状態遷移
- SQLite / PostgreSQL 共通 repository 契約
- ZIP 安全展開と上限判定

### 13.2 バックエンド統合

- Alembic 空 DB → head
- 旧版 → head
- 選定 DB 上での migration / rollback
- レガシー DB preview / commit
- 移行元画像・`cover_local_path` が持ち込まれないこと
- 同じ移行の再実行
- 取込途中失敗の rollback
- `meta2.db` との ASIN 状態合成
- 2 エージェント同時 claim
- エージェント認証失敗
- manifest 不一致
- パストラバーサル拒否
- `.partial` を処理せず `.ready` だけを取り込む
- Linux inbox → 正式領域の失敗時 rollback
- 選定 DB の backup / restore test

### 13.3 フロントエンド

- ページング・フィルタ・URL 復元
- 取込確認ダイアログ
- 強制再取込の ConfirmDialog
- 移行 preview と commit の分離
- 候補を選ぶまで紐付け API を呼ばない
- キャプチャジョブ作成
- 実行中・失敗・完了表示
- API エラーの sonner 通知

### 13.4 実データ受入

- レガシー移行の preview / commit 件数一致
- 購入書籍一覧の無作為標本確認
- comic / novel / other の分類標本確認
- 購入 / KU / 返品標本確認
- 既存画像 47 冊の人手確定
- comic / novel 各 1 冊の新規キャプチャ
- Windows → Linux Samba inbox 転送の中断・再送
- キャプチャ後のライブラリ表示、シリーズ表示、novel OCR 投入確認

## 14. 品質ゲート

各 Phase で該当範囲を実行し、Phase 6 では全件実行する。

```bash
cd backend && uv run pytest -q
cd backend && uv run ruff check .
cd frontend && npm run test
cd frontend && npm run lint
cd frontend && npx tsc -b
cd frontend && npm run build
uv run python scripts/maintenance/check_docs.py
```

OpenAPI を変更した Phase では backend を起動し、`cd frontend && npm run generate:types` も実行する。

## 15. セキュリティ・プライバシー

- ローカル/LAN の単一ユーザー運用を維持する
- Amazon 生データや購入履歴を外部サービスへ送信しない
- カード番号・支払手段を DB に保存しない
- 注文番号を API 一覧の既定応答や通常ログへ出さない
- 任意ファイルパスを HTTP から受け取らない
- レガシー DB は read-only で開く
- エージェント API は専用トークンを要求する
- Windows 用 Samba ユーザーは capture inbox だけに書き込み可能とする
- Windows は DB と正式画像領域へ直接アクセスしない
- `.ready` アーカイブは安全パス検証、symlink 拒否、サイズ・件数上限を通す
- キャプチャ出力先は Linux 側で `get_dirs_by_source()` と安全パス検証を通す
- PostgreSQL 採用時も DB ポートを LAN / Tailscale へ公開しない
- DB バックアップと検証済み復元手段を確認後に破壊的移行を行う
- 「全削除」「DB リセット」UI は初期実装に含めない

## 16. リスクと対策

| リスク | 対策 |
|---|---|
| タイトルだけでは既存画像を誤紐付けする | 候補提示のみ。確定は必ず人が行う |
| Amazon CSV の列が変わる | 必須列検証、未知列無視、形式別 fixture |
| 11,000 冊以上で画面が重くなる | サーバー側ページング、索引、Query Key 分離、Phase 0 の10倍/100万行ベンチ |
| 件数だけで PostgreSQL を導入し運用が複雑化する | 実測基準を満たす場合は既存 SQLite 運用を優先 |
| SQLite の同時書き込みが不足する | Phase 0 負荷試験で判定し、基準未達なら PostgreSQL を採用 |
| PostgreSQL のバックアップだけ未検証になる | custom dump + temporary database への週次 restore test を採用条件にする |
| 差分取込で手動修正が消える | 自動更新対象と手動保護フィールドを分離 |
| キャプチャジョブが二重実行される | 条件付き UPDATE による排他 claim |
| 中断転送がライブラリへ混入する | `.partial` は無視し、`.ready` だけを Linux が検証・展開 |
| Linux backend から Windows 操作できない | Windows キャプチャエージェントへ分離 |
| Samba inbox から正式領域へ不正ファイルが入る | 専用共有、安全なZIP展開、manifest照合、正式領域への直接共有禁止 |
| 別 DB がバックアップから漏れる | SQLite / PostgreSQL の選定結果に応じて server backup / restore test 対象に追加 |
| 旧機能と新機能が二重にメタ更新する | 新機能受入後に旧 API・ボタンを撤去 |

## 17. 最終 DoD

- Pic2PDF_Viewer だけで Amazon データを取り込める
- 購入カタログ・取込ジョブ・画像の正式配置が Linux サーバーを正本として動作する
- SQLite / PostgreSQL の採否が実測と ADR で説明できる
- `kindle購入履歴` アプリを停止・削除しても通常運用できる
- `kindle購入履歴` 側の表紙・画像キャッシュ・画像パスが移行されていない
- 購入書籍を comic / novel、所有状態、画像取込状態、シリーズで検索できる
- 既存画像 47 冊を ASIN に基づき整理できる
- 購入一覧からキャプチャジョブを作成できる
- Windows エージェントが選択した ASIN を維持し、Linux の専用 inbox へ成果物を転送できる
- Linux が成果物を検証して正式画像領域へ公開できる
- キャプチャ成功後に `books_meta` と購入カタログが ASIN で接続される
- 感想・レビュー・レビュースクレイピングが持ち込まれていない
- 移行・再取込・キャプチャ失敗からロールバックまたは再実行できる
- 全品質ゲートと実機スモークテストが通る
