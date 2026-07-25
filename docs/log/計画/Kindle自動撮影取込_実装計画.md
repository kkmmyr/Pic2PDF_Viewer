# Kindle 自動撮影取込 実装計画

作成日: 2026-07-25

状態: **Phase 4 購入書籍詳細・キャプチャUI完了（2026-07-25）**

バックログ: [B-34](バックログ.md)

要件: [Kindle 自動撮影取込 要件](../../design/要件定義/Kindle自動撮影取込_要件.md)

現行設計: [Kindle 購入カタログ設計](../../design/詳細設計/機能別/Kindle購入カタログ設計.md)

## 1. 目的

Kindle 購入カタログで選択した 1 冊を、起動済み Windows Kindle アプリで自動的に検索・照合し、必要ならダウンロードを待ち、表紙または先頭から最終ページまで撮影して Pic2PDFViewer へ登録する。

既存の capture job、capturer、Samba inbox、Linux 側検証・原子的配置を再利用し、現在手動の「対象書籍を Kindle で開いて確認する」工程を安全な自動操作へ置き換える。

## 2. 現状と変更境界

### 2.1 再利用する実装

- `backend/services/kindle_catalog/capture_jobs.py`
  - ジョブ作成、claim、条件付き状態遷移、成果物検証、正式配置、失敗時ロールバック
- `kindle-pdf/capture_agent.py`
  - ジョブポーリング、一時ディレクトリ、manifest 作成、`.partial` から `.ready` への転送、完了 API
- `kindle-pdf/capturer.py`
  - Kindle ウィンドウ検出、描画安定待ち、ページ送り、漫画撮影、最終ページ検出
- `kindle-pdf/novel_capturer.py`
  - 小説向けクロップと画像保存
- `frontend/src/hooks/useKindleCatalog.ts`
  - capture job 作成と 5 秒ポーリング
- `frontend/src/pages/KindleCapturePage.tsx`
  - 既存ジョブ表示

### 2.2 新規開発の中心

- Kindle の購入済みライブラリを操作する Windows UI Automation コントローラー
- ASIN、タイトル、著者、シリーズ・巻による本人照合
- 未ダウンロード書籍の完了待機
- 表紙または先頭位置への移動
- 自動準備工程を表すジョブ状態、heartbeat、エラー分類
- 購入書籍詳細からのジョブ開始と工程表示

### 2.3 維持する境界

- Kindle アプリは自動起動しない。
- ログイン、画面ロック解除、撮影中の端末併用には対応しない。
- Amazon データ、Kindle Info、旧 DB の取込ロジックを変更しない。
- 既存画像の ASIN を自動確定しない。
- Windows から Linux の正式画像領域へ直接書き込まない。
- 初期版は 1 冊ずつ処理し、複数選択と並列撮影を行わない。

## 3. 目標アーキテクチャ

```text
購入書籍の詳細
      │ capture job 作成（ASIN / source / direction）
      ▼
Linux: kindle_catalog.db
      │ claim + 書誌照合情報
      ▼
Windows: capture_agent
      │
      ├─ KindleAppController
      │    接続 → 検索 → 本人照合 → DL待ち → 開く → 先頭移動
      │
      └─ AutoKindleCapturer / NovelKindleCapturer
           撮影 → manifest → Samba *.partial → *.ready
                                      │
                                      ▼
Linux: 検証 → 正式画像配置 → meta2.db ASIN設定 → succeeded
```

Kindle UI 操作は capturer から分離する。capturer は「正しい書籍が先頭位置で開かれている」という事前条件だけを受け持ち、検索候補やダウンロード状態を認識しない。

## 4. ジョブ状態遷移

```text
queued
  └─ claim → claimed
                └─ locating_book
                     ├─ downloaded ─────────────┐
                     └─ not downloaded → downloading
                                                └─ complete
                                                     ▼
                                                positioning
                                                     ▼
                                                 capturing
                                                     ▼
                                              awaiting_files
                                                     ▼
                                                 succeeded

各実行状態 ── unrecoverable error / timeout / stale heartbeat → failed
```

既存の `waiting_user` は後方互換用の旧状態として読み取り可能にするが、新しい自動ジョブでは使用しない。既存状態を持つジョブを新しいエージェントが再開する規則は実装前にテストで固定する。

## 5. Phase 0 — Kindle 実機成立性検証

本番状態遷移や UI を変更する前に、対象 Windows 端末と実際の Kindle アプリで検証する。

### 5.1 検証項目

1. 起動済み Kindle プロセスとトップレベルウィンドウへ接続できる。
2. 購入済みライブラリと検索欄を UI Automation tree から識別できる。
3. ASIN検索が成立するかを確認する。
4. 検索結果から ASIN、タイトル、著者、シリーズ・巻の取得可能範囲を確認する。
5. 同名・類似タイトル、別巻を区別できる。
6. ダウンロード済みと未ダウンロードを判別できる。
7. 未ダウンロード書籍を開き、読書画面の表示完了を判定できる。
8. 読書途中の書籍を表紙または先頭位置へ戻せる。
9. ライト・ダーク、最大化状態、標準的な画面解像度で locator が安定する。

### 5.2 合格ゲート

- ASIN完全一致、または正規化タイトル + 著者／シリーズ・巻で一意に照合できる。
- 候補複数と照合情報不足を成功扱いにしない。
- ダウンロード完了と読書画面安定を機械判定できる。
- 絶対座標だけに依存せず対象候補を選択できる。
- 表紙または先頭への移動を繰り返し再現できる。

合格しない項目がある場合は、本実装へ進まず locator、照合契約、またはスコープを見直す。

### 5.3 成果物

- 対象 Kindle アプリのバージョンと検証環境
- 利用可能な UI Automation 要素と識別子
- 検索・照合方法の採否
- ダウンロード完了判定
- 先頭移動手順
- 失敗画面と復旧可否の一覧

### 5.4 実機調査結果（2026-07-25）

対象環境:

- Windows Store 版 `AMZNKindle.AmazonKindleReadingApp 1.0.18632.0`
- プロセス `Kindle.exe`
- トップレベルウィンドウ名 `Kindle`
- ウィンドウクラス `Microsoft.UI.Windowing.Window`
- 追加調査前のダウンロード済みローカル書籍は 11 冊。追加調査後は指定書籍を含む 12 冊
- 指定小説 `B0DJ3DYD7M` は実内容が小説でも、カタログ上は `comic`

判定: **条件付き合格**。ASIN 検索、本人照合、未ダウンロード書籍の取得、漫画・小説の先頭境界、既存 capturer の接続と小説クロップが実機で成立した。Phase 1 以降の本実装開始ゲートを開く。ただし、カタログ分類を撮影 `source` の正本にしないこと、UI Automation tree 全体を高頻度走査しないこと、小説の安全側クロップを許容することを実装条件とする。

#### 成立を確認した項目

1. ライブラリ検索欄は UI Automation の `ControlType.Edit`、名前 `検索ライブラリ` として公開され、`ValuePattern.SetValue()` で ASIN を入力できる。
2. ASIN 検索により通常 127 カードから対象を含む結果へ絞り込める。
3. 書籍カード内には `library-more-menu-<ASIN>` があり、対象 ASIN のカードを一意に特定できる。
4. 未ダウンロードカードには `download-button-<ASIN>` がある。ダウンロード済みカードでは同ボタンが消えるが、`library-more-menu-<ASIN>` は残る。
5. ダウンロード済み成果物は `%LOCALAPPDATA%\Packages\AMZNKindle.AmazonKindleReadingApp_m1sc522ngdk36\LocalState\Classic\Content\<ASIN>_EBOK` に配置される。実測例では `.voucher`、`.azw`、`.mbpV2`、`.phl`、`.res`、`.md` が存在し、待機中の `Data\Cache\book_temp_dl` は空だった。
6. 対象カードの `library-item-container` / `library-item-image` の実測矩形を使ってクリックし、書籍を開ける。画面上の固定座標は不要である。
7. 読書画面へ移行してもウィンドウハンドルとタイトル `Kindle` は維持され、既存 capturer の `find_window()` 条件と互換である。
8. 読書画面では `backButton`、`page-chevron-container-left`、`page-chevron-container-right`、`FooterLabelText`、`immersive-title` を取得できる。
9. Kindle のショートカット表示から、`PageUp` が「前のページ」、`PageDown` が「次のページ」、`Ctrl+W` がライブラリ復帰、`Ctrl+G` が位置移動として定義されていることを確認した。
10. 固定レイアウト漫画では `Home` と `Ctrl+G` は先頭移動に使えなかったが、読書領域へフォーカスした後に `PageUp` を反復すると読書開始側へ戻れる。
11. 実書籍で `ページ149/265` から 114 回戻り、`ページ265/265` で 3 回連続して変化しない先頭境界へ到達した。
12. `backButton` でライブラリへ戻り、検索値が空、127 カード表示へ復元した。
13. 指定された未ダウンロード書籍 `B0FTDGD2XV` を取得した。開始前は `<ASIN>_EBOK` が存在せず、開始直後は `download-button-B0FTDGD2XV` の accessible name が `ダウンロードをキャンセルする` に変化した。
14. 再ダウンロードでは開始から約 16 秒でダウンロードボタンが消え、`<ASIN>_EBOK` に 10 ファイル、合計 15,162,028 bytes が生成された。`.azw`、`.voucher`、`.mbpV2`、`.md`、複数の `.res` を確認した。
15. `Data\Cache\book_temp_dl` は監視中も空であり、完了判定には使えない。ダウンロードボタンの消失と、正式 `<ASIN>_EBOK` の必須ファイル存在・サイズ安定を併用する。
16. 指定されたダウンロード済み小説 `B0DJ3DYD7M` は ASIN 検索とカードのキーボードフォーカス + `Enter` で開けた。読書画面は `Location 1 of 2959 • 0%` で、`PageUp` を 3 回送っても変化せず先頭境界と判定できた。
17. 小説の次ページ操作は左側 `page-chevron-container-left`、前ページ操作は右側 `page-chevron-container-right` の実測矩形クリックで成立した。本文 `ページ13/233 • 3%` から右側操作で `Location 1 of 2959 • 0%` へ復元できた。
18. `NovelKindleCapturer` は先頭表紙で安全領域全体の `CROP=(170,105)-(3686,2023)`、本文ページで `CROP=(283,105)-(3590,2023)` を選択した。上下 UI は除外でき、無効矩形は発生しなかった。
19. 本文ページでは検出端の外側余白が 10 px で、切り抜き画像の左右端 20 px にも非白画素が残った。初期版は先頭表紙で選ばれる広い安全領域を維持して欠落防止を優先し、余白最適化は撮影結果を見て後続調整する。
20. 追加調査終了時は、指定ダウンロード書籍を取得済み、指定小説を先頭位置、Kindle をライブラリ表示、検索値を空へ復元した。

#### 実測から追加する実装制約

- `library-item-container`、ダウンロードボタン、戻るボタンは `ControlType.Button` でも `InvokePattern` を公開しない。AutomationId で要素を特定した後、その要素から取得した実測矩形をクリックする。
- `immersive-title` はカタログの正式タイトルと、NFKC・既存タイトル正規化後も一致または包含にならなかった。開いた後のタイトルを本人照合の正本にしない。
- 本人照合の正本は、既知 ASIN で検索し、同じ ASIN を含む `library-more-menu-<ASIN>` を持つカードを開くこととする。
- ページ送り直後の次入力は無視される場合がある。フッター変化後に約 2 秒の安定待ちを置き、変化なしは 1 回で境界判定せず最大 3 回再試行する。
- 右開き漫画では「前のページ」へ戻るとフッター番号と割合が増える。数値の大小ではなく、`PageUp` 後の変化が 3 回連続で止まったことを先頭境界とする。
- 読書領域がキーボードフォーカスを失うと `PageUp` が無視される。先頭移動前に、UI Automation で取得した読書領域またはフッター矩形をクリックしてフォーカスを確保する。
- ダウンロード中も AutomationId は `download-button-<ASIN>` のまま、accessible name が `ダウンロードをキャンセルする` へ変わる。`downloading` はこの名前で判定し、完了はボタン消失と正式ファイル安定の AND 条件にする。
- カタログの `book_type` は誤分類を含む。指定小説 `B0DJ3DYD7M` も `comic` だったため、購入書籍詳細で `comic` / `novel` を利用者が変更し、capture job の `source` を明示確定する。
- UI Automation の全 descendants を約 100 ms 間隔で走査した調査中、完了約 41 秒後に Kindle が `ucrtbase.dll`、例外 `0xc0000409` で異常終了した。因果関係は断定できないが、本実装は AutomationId を指定した `FindFirst` と低頻度ポーリングを使い、プロセス消失を `kindle_app_exited` として失敗させる。
- 小説の先頭表紙では白背景検出が成立せず、安全領域全体へフォールバックする。初期版は画像欠落防止を優先してこの広いクロップを許容し、狭い動的クロップを成功条件にしない。

#### Phase 0 ゲート結果

- [x] 指定された未ダウンロード書籍 1 冊で、ダウンロード開始、進行中表示、完了を確認した。
- [x] ダウンロードボタンと正式 `<ASIN>_EBOK` の遷移を記録し、UI とファイルの 2 系統で完了条件を定義した。
- [x] 指定されたダウンロード済み小説 1 冊で、ASIN 検索、オープン、先頭境界を確認した。
- [x] 小説の先頭と本文で既存 `NovelKindleCapturer` のクロップ境界検出を確認した。

ネットワーク遮断による実エラーは端末全体へ影響するため誘発していない。`download_timeout` は設定期限超過、`download_failed` はエラー表示またはプロセス存続中のダウンロード状態消失、`kindle_app_exited` はプロセス消失として自動テストと実装後の制御試験で固定する。

## 6. Phase 1 — ジョブ契約とバックエンド

### 6.1 書誌照合情報

agent の claim 応答へ、既存カタログ DB から次を合成する。

- ASIN
- 正式タイトルと正規化タイトル
- 著者
- シリーズ名
- 巻番号、巻ラベル

照合情報は capture job に重複保存せず、原則として claim 時に既存テーブルから取得する。ジョブ履歴としてスナップショット保持が必要と Phase 0 で判明した場合だけ、migration を追加する。

### 6.2 状態と heartbeat

- `locating_book`、`downloading`、`positioning` を状態遷移へ追加する。
- active job の範囲と同一 ASIN の重複防止条件を新状態へ拡張する。
- agent 専用 heartbeat API と `heartbeat_at` を追加する。
- stale 判定時間を設定値とし、期限切れジョブを `failed` へ回収する。
- `started_at` は撮影開始時、`completed_at` は成功・失敗の確定時とする。

### 6.3 エラーコード

次を個別コードとして返し、任意の例外文字列だけに依存しない。

- `kindle_not_running`
- `kindle_ui_unavailable`
- `kindle_app_exited`
- `book_not_found`
- `book_match_ambiguous`
- `book_identity_unverified`
- `download_failed`
- `download_timeout`
- `positioning_failed`
- `capture_failed`
- `transfer_failed`
- `registration_failed`
- `agent_heartbeat_timeout`

### 6.4 想定変更ファイル

- `backend/services/kindle_catalog/models.py`
- `backend/services/kindle_catalog/capture_jobs.py`
- `backend/services/kindle_catalog/repository.py`
- `backend/routers/kindle_catalog.py`
- `backend/routers/api_schemas.py`
- `backend/services/kindle_catalog/migrations/`
- `frontend/src/types/api.d.ts`（OpenAPI から再生成）

### 6.5 Phase 1 実装結果

- [x] `locating_book`、`downloading`、`positioning` を active 状態へ追加し、旧 `waiting_user` 経路を後方互換で維持する。
- [x] `capture_jobs.heartbeat_at` の Alembic migration を追加する。
- [x] claim 応答へカタログ正本から合成した ASIN、正式・正規化タイトル、著者、シリーズ、巻の `identity` を追加する。
- [x] heartbeat API と、次回 claim 時の stale job 回収を追加する。
- [x] `KINDLE_CAPTURE_HEARTBEAT_TIMEOUT_SEC` を既定 300 秒のサーバー設定として追加する。
- [x] `kindle_app_exited` を含む工程別エラーコードを API で保持できる。
- [x] OpenAPI 生成型と backend の状態遷移・identity・heartbeat・stale 回収テストを更新する。

Phase 1 では Windows agent の手動確認処理を変更しない。自動検索・ダウンロード・先頭移動と定期 heartbeat 送信は Phase 2・3 でこの契約へ接続する。

## 7. Phase 2 — Kindle 操作コントローラー

`kindle-pdf/` に Kindle UI 操作を担当するモジュールを追加する。

### 7.1 責務

- `attach_running_app()`
- `open_library()`
- `search_book(identity)`
- `collect_candidates()`
- `verify_candidate(identity, candidate)`
- `wait_for_download(timeout)`
- `open_book()`
- `go_to_start()`
- `wait_for_reader_stable()`

公開メソッド名は実装時に調整してよいが、検索・本人照合・ダウンロード・読書位置調整を capturer へ混在させない。

### 7.2 実装方針

- Windows UI Automation の意味的な要素識別を第一候補とする。
- `pyautogui` は既存のページ送りや、UI Automation で代替できない限定操作に閉じ込める。
- locator は 1 箇所へ集約し、Kindle 更新時の修正範囲を限定する。
- 各工程にタイムアウトを設ける。
- 失敗時は工程、locator、取得できた候補数を診断ログへ残す。
- 書名や購入情報を大量にログへ出さず、必要な場合も長さを制限する。

### 7.3 想定変更ファイル

- `kindle-pdf/kindle_app_controller.py`（新規）
- `kindle-pdf/capture_agent.py`
- `kindle-pdf/pyproject.toml`
- `kindle-pdf/tests/`

### 7.4 Phase 2 実装結果

- [x] 起動済み `Kindle.exe` と対応ウィンドウだけへ接続し、アプリを自動起動しない。
- [x] ASIN検索と `library-more-menu-<ASIN>` の最大2件限定探索で、候補なし・複数・本人照合不足を区別する。
- [x] ASINなしの純関数照合として、正規化タイトル + 著者またはシリーズ・巻の一致条件を固定する。
- [x] ダウンロードボタンと正式コンテンツフォルダの安定を併用し、失敗とタイムアウトを区別する。
- [x] `FooterLabelText` の変化停止を3回確認する先頭移動を実装する。
- [x] 指定漫画 `B08M8XZWM7` で接続、ASIN検索、一意照合、ダウンロード済み判定を実機確認する。

## 8. Phase 3 — capture agent 統合

1. claim 後に `waiting_user` へ進める現在の確認ダイアログを自動操作へ置き換える。
2. Kindle 未起動は `kindle_not_running` で終了する。
3. `locating_book` で検索・本人照合する。
4. 未ダウンロードなら `downloading` へ進み、完了後に再照合する。
5. `positioning` で書籍を開いて先頭へ移動する。
6. 読書画面安定後に `capturing` へ進み、既存 capturer を起動する。
7. 既存の package 公開と完了 API を維持する。
8. 各長時間工程で heartbeat を更新する。

再実行は failed job を同じ ID で巻き戻さず、新しい job を作成する。agent 再起動時は stale job を暗黙再開せず、サーバーの回収結果に従う。

### 8.1 Phase 3 実装結果

- [x] 旧確認ダイアログを削除し、controllerによる検索・照合・ダウンロード・先頭移動へ置き換える。
- [x] controller例外、撮影、転送、登録を工程別エラーコードへ変換する。
- [x] 独立heartbeat workerを追加し、長時間待機と撮影progress callbackから送信失敗を検出する。
- [x] 撮影1枚目と5枚ごとに `capturing → capturing` で `captured_screens` を更新し、初回 `started_at` を保持する。
- [x] `awaiting_files` だけ完了APIを再試行し、それ以前の途中状態は新規job作成を要求する。
- [x] `.partial` 転送失敗時のcleanupと `.ready` 原子的renameを自動テストで固定する。

## 9. Phase 4 — フロントエンド

### 9.1 購入書籍詳細

- 利用準備中表示を「撮影して取り込む」操作へ置き換える。
- タイトル、ASIN、著者、シリーズ・巻、source、方向を確認する。
- カタログの `book_type` を source の初期値にするが、誤分類に備えて `comic` / `novel` を利用者が変更できる。
- 運用前提を確認ダイアログに表示する。
- job 作成成功後はキャプチャページへ移動できる。
- 同一 ASIN の active job がある場合は新規作成を無効化し、既存 job を案内する。

### 9.2 キャプチャページ

- active、failed、succeeded を区別する。
- 自動準備工程を日本語で表示する。
- 経過時間、撮影済み画面数、エラー説明、再実行前の確認事項を表示する。
- 5 秒ポーリングを維持する。
- iPad 相当幅では開始操作より状態閲覧を優先するが、端末判定で操作を禁止しない。

### 9.3 想定変更ファイル

- `frontend/src/components/kindle/KindleBookDetailDialog.tsx`
- `frontend/src/pages/KindleCapturePage.tsx`
- `frontend/src/hooks/useKindleCatalog.ts`
- `frontend/src/components/kindle/kindle-labels.ts`
- `frontend/src/test/KindleCatalogPage.test.tsx`

### 9.4 Phase 4 実装結果

- [x] 購入書籍詳細でsourceとページ送り方向を変更し、運用前提の確認後にjobを作成する。
- [x] 同一ASINのactive jobとmutation送信中は開始操作を無効化し、既存jobへの導線を表示する。
- [x] 取込済み書籍は上書き撮影を無効化し、初期版の対象外であることを表示する。
- [x] キャプチャページで工程説明、経過時間、撮影画面数、依頼・完了日時、agent、成功結果を表示する。
- [x] 失敗コード別の日本語対処と、確認ダイアログを経由する新規job再実行を追加する。
- [x] loading・empty・error・disabled・active・failed・succeededをレスポンシブな1画面で扱う。

## 10. Phase 5 — テストと段階導入

### 10.1 自動テスト

- Kindle 操作コントローラーの候補照合純関数
- ASIN完全一致、タイトル正規化、著者、シリーズ・巻の一致
- 候補なし、候補複数、情報不足
- ダウンロード完了、タイムアウト、予期しない画面
- ジョブ状態遷移、重複防止、heartbeat、stale 回収
- capture agent の工程別エラーコード
- 完了時の manifest 検証と原子的配置
- 失敗時に正式画像領域と `meta2.db` が不変
- UI の開始確認、状態ラベル、エラー、二重送信防止

### 10.2 実機マトリクス

| ケース | comic | novel |
|---|---:|---:|
| ダウンロード済み | 必須 | 必須 |
| 未ダウンロード | 必須 | 必須 |
| 読書途中から先頭へ移動 | 必須 | 必須 |
| 類似タイトル・別巻 | 必須 | 代表 1 件 |
| Kindle 未起動 | 共通で必須 | 共通で必須 |
| ダウンロードタイムアウト | 共通で必須 | 共通で必須 |
| agent 異常終了・stale 回収 | 共通で必須 | 共通で必須 |

### 10.3 UI 受入

- デスクトップでジョブ作成、状態監視、成功、失敗、再実行を確認する。
- iPad 縦横相当幅でジョブ状態を閲覧できる。
- ライト・ダーク、loading、empty、error、disabled、success を確認する。
- キーボード操作、フォーカス表示、accessible name を確認する。

### 10.4 実環境の成果物転送

- 既存 Samba 共有 `pic2pdf-input` 配下の
  `.kindle-capture-inbox` を論理専用受信箱として使う。
- `DoujinWatcher` はトップレベルの隠しディレクトリを無視し、Kindle成果物を
  同人誌生成へ渡さない。
- Linux と Windows は同じ実体を、それぞれローカルパスと UNC パスで参照する。
- `comic/images` / `kindle_novel/images` の正式領域は Samba 公開しない。

### 10.5 実機で判明した先頭移動の互換性

- Microsoft Store版 Kindle 1.0.18632.0 の漫画読書画面では、
  `ReadingArea` は取得できるが `FooterLabelText` が存在しない。
- フッター文字列へ依存した初回実行は `kindle_ui_unavailable` で撮影前に安全停止した。
- `ReadingArea` の画像差分によるページ変化・境界判定へ切り替え、同じ書籍で再試験する。
- 読書画面への遷移直後にUI Automation列挙が一時的な `COMError` を返す実測も確認した。
  control探索では未検出として再pollし、遷移完了後の安定要素を取得する。

## 11. 実装順序とコミット境界

1. `docs:` 要件・計画・設計参照の確定
2. `test:` Phase 0 の検証手順と照合テストケース
3. `feat:` backend の状態・heartbeat・agent 契約
4. `feat:` Kindle 操作コントローラー
5. `feat:` capture agent 統合
6. `feat:` 購入書籍詳細とキャプチャページ
7. `test:` 実機受入結果と回帰テスト
8. `docs:` 現行設計への昇格、計画完了記録、変更履歴

Phase 0 が不合格の場合は 3 以降へ進めず、検証結果だけを記録して要件または方式を再検討する。

## 12. 完了条件

- [ ] [要件定義の受入条件](../../design/要件定義/Kindle自動撮影取込_要件.md)をすべて満たす。
- [ ] backend、frontend、kindle-pdf の関連テスト、lint、型検査が成功する。
- [ ] 実機マトリクスを完了し、対象 Kindle アプリのバージョンを記録する。
- [ ] 現行設計書と API 仕様を実装済みの現在形へ更新する。
- [ ] `docs/log/変更履歴.md` へ実装・実機受入結果を追記する。
