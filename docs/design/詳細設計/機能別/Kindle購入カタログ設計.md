# Kindle 購入カタログ設計

> status: living | last-verified: 2026-08-10

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

### 4.1 Amazon エクスポートのバージョン選択

Amazon の Kindle エクスポートでは、従来の `_FE.csv` 名に代わり、同じ論理データが
`.1.1` / `.2.2` / `.3.1` などのバージョン付きファイルとして同梱される場合がある。
medaroserver へ配置する前に、列構成とデータ件数を確認し、書籍本体を含む完全な
バージョンを1つだけ選択して、バックエンドが認識する正規名へコピーする。
複数バージョンを結合・同時配置しない。

2026-07-30 生成データでは次を確認した。

| 論理データ | 採用元 | 配置時の正規名 |
|---|---|---|
| 取得日・所有関係 | `Kindle.UnifiedLibraryIndex.CustomerRelationshipIndex.3.1.csv` | `Kindle.UnifiedLibraryIndex.CustomerRelationshipIndex_FE.csv` |
| ジャンル | `Kindle.UnifiedLibraryIndex.CustomerGenres.3.1.csv` | `Kindle.UnifiedLibraryIndex.CustomerGenres_FE.csv` |
| 著者 | `Kindle.UnifiedLibraryIndex.CustomerAuthorNameRelationship.3.1.csv` | `Kindle.UnifiedLibraryIndex.CustomerAuthorNameRelationship_FE.csv` |

`CustomerRelationshipIndex.3.1` は11,727行・有効ASIN 11,700件超を持つ本体データで、
`1.1` は11行・有効ASIN 3件、`2.2` は8行・有効ASIN 0件だった。`1.1` の有効ASINは
すべて `3.1` に含まれ、旧版は Collection Follow / Customer Metadata / Sample Owner
中心であるため取り込まない。3系列のCSVヘッダーは従来 `_FE` ファイルと一致する。

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

`PUT /api/kindle-catalog/links` は `book_id` と ASIN を受け、対象が `comic` または `novel` であること、ASIN がカタログに存在することを検証した後、既存フィールドを保持して `meta2.db.books_meta.asin` だけを更新する。

## 7. キャプチャ連携

本節をLinux backend、Windows capture agent、シリーズ実行scriptをまたぐjob契約の正本とする。
Windows UI Automation、撮影矩形、ページ送り、package生成の内部設計は
[`kindle-pdf/docs/detailed_design.md`](../../../../kindle-pdf/docs/detailed_design.md)を参照する。
利用者から見た開始・停止・再実行条件は
[Kindle 自動撮影取込 要件](../../要件定義/Kindle自動撮影取込_要件.md)を正とする。

### 7.1 job状態と所有権

画面から作成した `capture_jobs` は Linux DB が正本となる。Windows エージェントは 1 件ずつ claim し、claim 応答の `identity`（ASIN、正式・正規化タイトル、著者、シリーズ、巻）を使って対象書籍を照合する。

状態遷移は `queued → claimed → locating_book → downloading（必要時）→ positioning → capturing → awaiting_files → succeeded` とし、各実行状態から `failed` へ遷移できる。既存 Windows エージェントとの段階導入互換性のため、`claimed → waiting_user → capturing` も読み書き可能な旧経路として維持する。

claim と状態更新時に `heartbeat_at` を更新し、agent は長時間工程中に heartbeat API を呼ぶ。次回 claim 時に、`KINDLE_CAPTURE_HEARTBEAT_TIMEOUT_SEC`（既定 300 秒）を超えた active job を `agent_heartbeat_timeout` で `failed` へ回収してから次の queued job を選ぶ。同一 agent が期限内に再 claim した場合は、現在の active job を返す。

成果物は Samba 上の論理専用受信箱へ `.partial` 名で送信し、完了後に
`.ready` へ rename する。既存環境では
`pic2pdf-input/.kindle-capture-inbox` を利用し、同人誌監視の対象から除外する。
Linux は `.ready` だけを検証し、安全な相対パス、許可拡張子、件数・容量上限に加えて、
version 2 manifest のjob identity、SHA-256、画像復号・寸法・連番を実ファイルから再計算し、
撮影完了証跡、撮影前カナリア、登録前画像QAは形式と内部整合を検証してから正式配置する。
終端観測フレームとカナリア画像はpackageに含めないため、意味判定はWindows側で行う。
Windows側の合否だけを信用せず、証跡欠落・不一致・blocking候補ありの場合は正式画像領域とDBを更新しない。登録は `awaiting_files` かつclaimしたagent所有のjobだけに許可し、正式画像の置換と `succeeded` 更新を同じ完了処理で確定する。失敗時は既存の正式画像とDBを保持する。

現行Windows agentは、起動済みKindleへの接続、ASINの一意照合、必要時のdownload、位置決め、撮影、転送、登録を1冊ずつ直列実行する。旧 `waiting_user` は後方互換契約として読み書き可能に残すが、現行agentは使用しない。内部の入力方式やUI control識別を横断契約に含めない。

撮影後・共有前に件数を検証し、`expected_screens`指定時は指定件数、未指定時は
小説50画面・漫画10画面を最低件数とする。未満なら`capture_incomplete`として
一時成果物を破棄し、既存の正式画像を置換しない。

正式撮影前には同じsource・ページ送り方向・撮影矩形で2画面のカナリアを実行する。
撮影後は最大32ページを等間隔に標本化し、内容の異なる複数ページの外周で同一座標の
構造化タイルが反復する画面オーバーレイを検査する。隣接2タイル以上が標本の50%以上で
反復する高信頼候補は`capture_incomplete`として拒否し、20%以上50%未満は
`repeated_screen_overlay_candidate` warningとしてversion 2 manifestへ残す。
完全重複、低容量、白紙・疎な画面、隣接dHash近似重複、小説上下端の内容密度は
誤検知校正中のためwarningに留め、自動削除や登録拒否には使用しない。

2026-08-22の未調整実画像holdoutでは、検出結果を参照せず固定seedとタイトルfamily hashだけで
漫画2冊・小説2冊（524画面）を選び、全画像SHA-256を先に封印した。Codex画像QAでは撮影欠陥を
0件と判定した一方、近似重複5、白紙・疎6、低容量13、小説端密度2の計26 warningが出た。
したがって、これらを欠陥として扱った暫定適合率は0%であり、完全重複以外のraw warningを
blockingへ昇格しない。固定seedで完全重複・白紙化・微差重複・25%上端切れを各1件注入した
制御故障では5 codeすべてrecall 1.0だったが、実陽性の人手labelを代替する根拠にはしない。

警告UIを追加する場合は登録成功と分離した「要確認候補」とし、書籍・code単位で件数をまとめ、
対象ページを開けるようにする。失敗toast、自動削除、OCR開始の自動停止には流用せず、章扉・表紙・
挿絵・奥付等の正常例を含む旨を明示する。現行manifestのwarningは登録後に永続化されないため、
UI実装前に保存先、既読状態、再監査時のpolicy version更新規則を別途設計する。

### 7.2 シリーズ直列実行

`scripts/capture_kindle_series.py` は購入カタログAPIだけを正本として、対象を巻順に並べ、
常に1冊分のjobだけを作成する。APIもjob作成transaction内で全source・全ASINの未完了jobを
最大1件に制限する。jobが `succeeded` になり、対象ASINの `capture_state=captured` を
再取得できた場合だけ次へ進む。`failed`、監視timeout、API不整合、割り込み、登録状態不一致では
後続jobを作成しない。監視側の停止は実行中jobを暗黙にcancelしない。

`capture_kindle_series.py`は旧CLI・import pathを保つfacadeとし、実装責務を次へ分ける。

- `kindle_series_inventory.py`: catalog itemの絞り込み、source・巻数決定、並び順。
- `kindle_series_session.py`: manifest digest、session state、atomic永続化、breaker。
- `kindle_series_screen_count.py`: 成功実績の選別、source別中央値、warning contract。
- `kindle_series_orchestrator.py`: 1冊ずつのjob作成・監視・限定復旧・登録確認。
- `kindle_series_http.py`: 購入カタログAPI transport。
- `kindle_series_cli.py`: 引数検証、依存組み立て、exit code変換。

orchestratorはHTTP実装へ依存せず`CaptureApi` protocolだけを参照する。session breakerは
job作成前に検査し、inventory・CLI・HTTP adapterからKindle UIを直接操作しない。

既定はdry-runで、実行には `--apply` とsession stateを要求する。state schema v2は対象manifest digest、
完了ASIN、ASIN別撮影画面数、品質warning、復旧回数、停止理由をatomic置換JSONへ保存し、既存stateは `--resume-session` を
明示した場合だけ、同じmanifestかつrunning状態で再開する。resume時は完了ASINと
画面数の1対1対応、warningのASIN・source・撮影数と観測値の一致を再検査する。必須fieldがない
schema v1や不整合stateは暗黙移行せずresumeを拒否し、実行状況を確認してから新規stateを作る。

画面数外れ値policy `kindle-series-screen-count-v1` は、対象inventory内で最新の
`succeeded` jobが確認できる登録済みASINと、実行中sessionの完了ASINをreferenceとする。
`comic` / `novel` は混ぜず、同sourceの正の画面数が3冊以上ある場合に限り、新しい
画面数が中央値の0.5倍未満または2倍超なら
`series_screen_count_outlier_candidate` warningを生成する。warningにはpolicy version、
ASIN、source、撮影数、reference冊数・最小・中央値・最大、比率を固定する。長編・短編や
特典巻の正常差を考慮し、初期policyは登録取消、session breaker、後続job停止に使わない。
撮影成功応答の画面数が正の整数でない場合はwarningとして集計せず、API不整合としてfail closedする。

Kindle processの自動復旧は `--recover-kindle-crash` 指定時だけ許可する。撮影開始前・撮影枚数0・
process消失・許可error codeを同時に満たし、再起動後に同一ASINを一意照合でき、他の未完了jobが
ない場合だけ、新しいjobを最大1回作る。processが残るUI不調、download・位置決め・撮影・転送・
登録失敗では復旧せずfail closedとする。現行runnerはerror種別にかかわらず1冊目の失敗で停止し、
連続download失敗を跨いだ自動継続は行わない。

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

初回移行完了後の通常運用 UI は [Kindle 購入カタログ画面 UI/UX 改善 要件](../../要件定義/Kindle購入カタログ画面_UI改善_要件.md) に従い、購入書籍、画像紐付け、キャプチャ、取込・管理の 4 ページへ分離する。各ページは Kindle 領域内の共通サブナビゲーションと固有 URL を持ち、購入書籍を初期ページとする。

フロントエンド実装は`features/kindle/`を所有境界とする。`api.ts`はHTTP、`queries.ts`は
TanStack Queryとinvalidate、`types.ts`はOpenAPI生成型alias、各`*Screen.tsx`は表示と
操作controllerを所有する。route pageはscreenを配置するだけとし、URL、query key、
invalidate範囲、toast文言、responsive layoutをこの再配置では変更しない。

- 購入書籍は検索中心の高密度テーブルとし、行から書籍詳細パネルを開く。
- 画像紐付けは Pic2PDFViewer の既存画像と Kindle カタログ候補を 2 カラムで比較し、最終確認後だけ ASIN を設定する。
- 購入書籍の詳細から対象、source、ページ送り方向、運用前提を確認して新規 job を作成する。同一 ASIN の active job または取込済み書籍では開始操作を無効化する。
- 他ASINに未完了jobがある場合、現行UIは開始ボタンを事前無効化しないが、backendが全source・全ASINで未完了job最大1件を強制して400で拒否する。全体active状態の事前表示・無効化は後続UI課題とする。
- キャプチャページは active / failed / succeeded の工程、経過時間、撮影画面数、失敗別対処を表示し、failed job は確認ダイアログから新しい job として再実行する。
- 取込・管理は既存 3 API の順次実行と個別実行、最終結果、旧 DB 移行を集約する。
- 購入書籍の検索語、フィルター、ページ、ページ件数は URL クエリを正本とし、検索入力だけ 300ms のデバウンスを持つ。
- queryの許容値、既定25件、25/50/100件、正のpage検証、条件変更時のpage resetは
  `features/kindle/catalog-query.ts`を正本とする。URL更新は元の
  `URLSearchParams`を変更せず新しい値を返し、reloadと戻る・進むで同じ条件を復元する。
- iPad 相当幅では購入一覧の著者をタイトル・ASINの下へ移し、種別・所有状態・画像状態をその下のバッジへまとめる。画像紐付けの 2 カラムは縦積みにし、端末種別による情報・機能の制限は行わない。

4ページへのUI再構成自体は既存 API、DB スキーマ、取込ロジックを変更していない。後続の自動撮影取込では capture job 状態、heartbeat、agent API を拡張したが、Amazonデータ取込、既存画像の自動ASIN確定、旧アプリ画像・表紙・レビュー移行は変更していない。
