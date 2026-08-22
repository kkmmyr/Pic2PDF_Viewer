# hitomi.la 新着監視設計書

> status: living | last-verified: 2026-08-22

Owner: hitomi monitor

特定作者の新着ギャラリーを低頻度で検出し、Pic2PDFViewer の UI で新着・既読履歴を確認する機能の現行契約。
API の完全な一覧と schema は実行中 FastAPI の`/openapi.json`と`/docs`を正本とし、OpenAPIで表せない意図は
[API設計](../API.md)を参照する。旧 API 詳細・外部仕様調査・systemd 手順は
[設計運用履歴](../../../archive/検証/hitomi新着監視_設計運用履歴.md)を参照する。

## 1. 境界と前提

- 個人 LAN・単一利用者向け。監視データは個人視聴履歴としてリポジトリへ含めない。
- 監視 CLI は単発 process とし、Linux では systemd timer から起動する。FastAPI の常駐を前提にしない。
- hitomi.la の NOZOMI は非公式な内部形式であり、URL・形式変更を障害として検知できるようにする。
- 低頻度・低帯域の個人利用だけを想定し、再配布や商用利用は対象外とする。
- Discord 通知は任意。Webhook 未設定時は no-op、通知失敗で監視結果を失敗にしない。

## 2. 構成とデータフロー

```text
systemd timer / 手動API
  -> backend/tools/hitomi_monitor.py
     -> watchlist.json
     -> monitor.lock取得
     -> NOZOMI ID取得
     -> gallery metadata取得
     -> meta2.db.hitomi_arrivalsへ追加
     -> state.json更新
     -> 任意のDiscord通知

FastAPI /api/hitomi/*
  -> watchlist.json + state.json + meta2.db
  -> React /hitomi
```

監視1回の順序は次の通り。

1. `watchlist.json`を読み、作者と言語ごとに NOZOMI の先頭 ID 群を取得する。
2. big-endian 32bit整数として decodeし、前回`top_id`との差分と`pending_gallery_ids`を重複排除して候補にする。
3. 候補 ID の gallery metadata を取得し、成功分を`hitomi_arrivals`へ冪等追加する。
4. `state.json`へ作者別`top_id`、`checked_at`、失敗IDと全体の実行結果を保存する。
5. 設定済みなら件数だけを Discord へ通知する。

個別 metadata 取得失敗は他 ID を止めず、失敗IDを`pending_gallery_ids`へ残して次回再試行し、全体 status を
`partial`にする。NOZOMI 自体の取得・decode失敗は作者単位の失敗として記録し、前回 state を失わない。

## 3. 永続データ

### 3.1 `watchlist.json`

作者ごとに`display_name`、内部識別子`normalized`、`language`、`added_at`を持つ。
`normalized`はtrim・小文字化・空白の`_`置換後、`_-`を保持してpercent-encodeしたNOZOMI keyである。
表示名や未encode文字列とは分離する。

### 3.2 `state.json`

全体の`last_run_at`、`last_run_status`（`ok / partial / error / never`）、`last_error`と、
`<normalized>:<language>`ごとの`top_id`、`checked_at`、`pending_gallery_ids`を持つ。旧stateに
`pending_gallery_ids`がない場合は空配列として扱い、書込時に現行形式へ更新する。

JSON 更新は同一ディレクトリの一時ファイルへ UTF-8 で書き、`flush`、`fsync`、`os.replace`の順で
原子的に置換する。失敗時は既存ファイルを保持する。

### 3.3 `meta2.db.hitomi_arrivals`

`gallery_id`を主キーとし、作者、表示名、タイトル、言語、種別、ページ数、公開日時、検出日時、URL、
既読状態、既読日時を保存する。既読化は`is_read`と`read_at`を同一 transaction で更新し、行を削除しない。

旧`new_arrivals.json`は`INSERT ... ON CONFLICT DO NOTHING`で1 transaction内に移行する。
移行元の path、mtime、size を`hitomi_legacy_imports`へ記録し、未変更なら再走査しない。旧 JSON は
可搬バックアップとして残すが、新規書込の正本にはしない。

## 4. 実装責務

| パス | 責務 |
|---|---|
| `backend/tools/hitomi_monitor.py` | 単発監視の orchestration と exit code |
| `backend/services/hitomi/nozomi.py` | URL構築、Range取得、big-endian decode |
| `backend/services/hitomi/metadata.py` | gallery metadata取得・parse |
| `backend/services/hitomi/watchlist.py` | 監視対象の正規化とCRUD |
| `backend/services/hitomi/state_store.py` | 実行状態の原子的保存 |
| `backend/services/hitomi/process_lock.py` | API／CLI／systemd共通のprocess間排他 |
| `backend/services/hitomi/arrival_store.py` | 検出履歴CRUDと旧JSON移行 |
| `backend/services/hitomi/notify.py` | 任意Discord通知。監視成否から分離 |
| `backend/routers/hitomi.py` | OpenAPI契約、排他、service呼出し |
| `frontend/src/pages/HitomiPage.tsx` | 新着・履歴・監視対象の画面構成 |
| `frontend/src/hooks/useHitomiArrivals.ts` | 一覧、既読化、一括既読、即時実行 |
| `frontend/src/hooks/useHitomiWatchlist.ts` | 監視対象の取得・追加・削除 |

router は path 安全性、入力検証、HTTP status、response model を担当し、外部取得や永続化ロジックを持たない。
同期`run-now`は process 内 lock で同一backend内の競合を先に拒否し、監視本体はdata directoryの
`monitor.lock`を非blocking取得してAPI／CLI／systemd間の競合を拒否する。別process実行中はCLI exit code 3、
API 409とする。lock fileは削除せず、Unixは`flock`、Windowsは`msvcrt.locking`の所有状態だけを解放する。

## 5. API と UI

機能上の API は、新着・既読一覧、個別／一括既読化、監視リストCRUD、即時監視、ヘルス表示である。
path、query、response schema は手書きで複製せず`/openapi.json`を正本とする。

UI は`/hitomi`で未読・既読・全件を切り替え、件数、監視最終時刻、status、errorを表示する。
galleryは外部 URL を新規タブで開く。既読化は物理削除ではなく履歴へ移動し、監視対象の削除でも
既存 arrival を削除しない。

## 6. 外部仕様と障害時挙動

- NOZOMI は ID を新着順に並べた4byte big-endian配列として扱う。取得件数上限を超える長期停止では
  取りこぼし得るため、監視間隔と取得件数を一緒に変更する。
- gallery metadata の JS wrapper を除去して JSON としてparseする。形式不一致は正常空配列にしない。
- URL／decode／metadata形式変更は`last_run_status`と`last_error`へ残し、UIとログから確認可能にする。
- gallery単位の重複はDB主キーで無害化する。DB batch保存後にstateを保存し、個別metadata取得に失敗したIDは
  `pending_gallery_ids`へ残す。次回はNOZOMI差分に現れなくても再試行し、成功してDB保存されたrunのstate更新で除去する。
- DB保存失敗時はstateを保存しない。state保存だけ失敗した場合は次回再試行し、DB主キーで重複を無害化する。
- Discord本文は件数だけとし、作品名や閲覧履歴を送らない。`HITOMI_DISCORD_WEBHOOK_URL`は`.env`から読む。

## 7. Linux運用

正本 unit は`deploy/hitomi-monitor.service`と`deploy/hitomi-monitor.timer`。配置後は`daemon-reload`し、
timerの有効化、次回時刻、service結果、アプリログを確認する。コマンド例や旧 Windows Task Scheduler 前提は
[設計運用履歴](../../../archive/検証/hitomi新着監視_設計運用履歴.md)へ置き、unit内容を本文へ複写しない。

`meta2.db`は日次 Online Backup と週次復元試験の対象に含める。`watchlist.json`と`state.json`も
個人データのバックアップ対象とし、復元時はDBとの時間差を許容して冪等再監視する。

## 8. 再検証トリガー

- NOZOMI URL、Range応答、ID decode、metadata wrapper の変更
- 監視間隔または取得件数の変更
- `hitomi_arrivals` schema、既読状態、旧JSON移行の変更
- systemd unit、データディレクトリ、バックアップ経路の変更
- Webhook送信内容または失敗時方針の変更
