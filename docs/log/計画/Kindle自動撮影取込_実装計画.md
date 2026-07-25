# Kindle 自動撮影取込 実装計画

作成日: 2026-07-25

状態: **計画確定・未着手**

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

## 9. Phase 4 — フロントエンド

### 9.1 購入書籍詳細

- 利用準備中表示を「撮影して取り込む」操作へ置き換える。
- タイトル、ASIN、著者、シリーズ・巻、source、方向を確認する。
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
