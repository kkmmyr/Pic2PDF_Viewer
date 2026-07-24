# hitomi.la 新着監視設計書

> status: living | last-verified: 2026-07-25

特定作者の新着ギャラリーを定期監視して、ライブラリ画面から確認・hitomi.la へのリンクで遷移できる機能の設計書。本機能は **既存の Pic2PDF_Viewer 本体機能とは独立** しており、設計上も実行プロセスとしても疎結合に組む。本機能に関する仕様・実装・運用はすべて本ファイルに集約する。

---

## 1. 機能概要

### 1.1. 目的

hitomi.la に登録された特定作者の **新着ギャラリーを自動的に検出**し、ユーザーが Pic2PDF_Viewer のライブラリ画面で一覧確認・hitomi.la へ直接リンクで飛べるようにする。

### 1.2. 主な動作

- ユーザーが UI から作者を **監視リスト** に登録
- バックグラウンドのスクリプトが週次（任意間隔）で監視リストを巡回し、新着 ID を検出
- 検出した新着のメタデータ（タイトル・ページ数・公開日等）を取得して保存
- ユーザーは UI の「新着」リンクから一覧を見て、`hitomi.la/galleries/<id>.html` を新規タブで開く
- 既読化操作で個別 / 一括非表示。既読作品は履歴タブから再確認でき、物理削除しない
- UI から「今すぐ取得」ボタンで Task Scheduler を待たずに監視スクリプトを手動実行できる（同期処理）

### 1.3. 制約・前提

- **NOZOMI は hitomi.la の内部仕様**であり、公式 API ではない。予告なく URL や形式が変わる可能性があるため、ヘルス情報を必ず記録し UI から状態確認できるようにする
- バックエンドサーバの常駐は **不要**（使うときだけ起動する運用を維持）
- 本機能のデータ（監視状態・新着履歴）は個人視聴履歴に近く、**リポジトリには含めない**（`.gitignore` 対象）
- 通知（メール・Discord 等）は **対象外**。UI 表示のみ

---

## 2. アーキテクチャ

### 2.1. 全体構成

```
┌─ Linux systemd timer (毎日 03:00 起動)
│    hitomi-monitor.timer → hitomi-monitor.service (oneshot)
│
└→ [hitomi_monitor.py]  ← 単発実行・終了
      │
      ├─ watchlist.json 読込
      ├─ NOZOMI 取得 (Range 数十バイト)
      ├─ 差分検出
      ├─ /galleries/<id>.js でメタデータ取得
      ├─ state.json に監視状態を書き出し
      └─ meta2.db の hitomi_arrivals に検出作品を追加
         (/opt/pic2pdf-viewer/data/)

[FastAPI] ──(SQLite + state.json 読込)──→ [新着 / 履歴画面 React]
                                          └→ hitomi.la/<id>.html へリンク
```

### 2.3. NOZOMI を使う理由

検索ページ `https://hitomi.la/search.html?artist:<name> language:japanese` の HTML は **クライアント側 JavaScript で結果を後付けレンダリング**するため、`curl` や WebFetch では空のシェルしか得られない。

NOZOMI は hitomi.la が事前生成して CDN に置いている、**条件にマッチするギャラリー ID 配列のバイナリファイル**。HTML レンダリングを回避でき、必要バイトも数十バイトで済むため、ポーリングコストが極小。

---

## 3. データフロー

```
[1] スクリプト起動
[2] watchlist.json から監視作者を読み込み
[3] 各作者ごとに:
    a. NOZOMI を Range 取得
       GET /n/artist/<artist_normalized>-<lang>.nozomi
       Range: bytes=0-79  (先頭 20 件)
    b. big-endian 4byte 整数として ID 配列にデコード
    c. state.json の前回 top_id と比較し、新規 ID を抽出
    d. 各新規 ID について /galleries/<id>.js を取得しメタを得る
    e. meta2.db.hitomi_arrivals に追加（gallery_id 重複は無視）
    f. state.json の top_id を更新
[4] state.json に last_run_at / last_run_status を記録
[5] 終了
```

UI 側は GET `/api/hitomi/new-arrivals?status=...` で SQLite を読み、新着 / 履歴を切り替える。

---

## 4. データ構造

`watchlist.json` / `state.json` の更新は、同一ディレクトリの一時ファイルへ
UTF-8 JSONを書き込み、`flush` + `fsync`後に`os.replace`する共通ヘルパーを使用する。
シリアライズ失敗・書き込み中断・置換失敗時も既存ファイルを残し、一時ファイルは削除する。

### 4.1. `watchlist.json`

```json
{
  "artists": [
    {
      "display_name": "aka shio",
      "normalized": "aka_shio",
      "language": "japanese",
      "added_at": "2026-04-29"
    }
  ]
}
```

- `display_name`: ユーザー入力そのまま（UI 表示用）
- `normalized`: 内部識別子（`state.json` のキー / 重複検出用）。小文字化 + 空白を `_` に置換した値。**URL とは別物**：URL に埋め込むときは `_` を空白に戻して URL encode する（§8.1 参照）

### 4.2. `state.json`

```json
{
  "last_run_at": "2026-04-29T03:00:00+09:00",
  "last_run_status": "ok",
  "last_error": null,
  "artists": {
    "aka_shio:japanese": {
      "top_id": 2034567,
      "checked_at": "2026-04-29T03:00:00+09:00"
    }
  }
}
```

- `last_run_status` の値: `ok` / `partial` / `error` / `never`
- `artists` のキーは `<normalized>:<language>`

### 4.3. `meta2.db.hitomi_arrivals`

```sql
CREATE TABLE hitomi_arrivals (
    gallery_id       INTEGER PRIMARY KEY,
    artist           TEXT NOT NULL,
    display_artist   TEXT NOT NULL,
    title            TEXT NOT NULL DEFAULT '',
    language         TEXT NOT NULL,
    gallery_type     TEXT NOT NULL DEFAULT '',
    page_count       INTEGER NOT NULL DEFAULT 0,
    published_at     TEXT,
    discovered_at    TEXT NOT NULL,
    url              TEXT NOT NULL,
    is_read          INTEGER NOT NULL DEFAULT 0 CHECK (is_read IN (0, 1)),
    read_at          TEXT
);
```

- `gallery_id` を主キーにし、再監視時の重複追加を無視する。
- 新規の既読操作は `is_read=1` と `read_at=<JST>` を同一transactionで更新する。
- 旧JSONには既読日時がないため、移行済み既読行は `is_read=1, read_at=NULL` とする。
- 既読行は自動削除しない。削除機能を追加する場合は別の明示操作として設計する。

### 4.4. 旧 `new_arrivals.json` の移行

FastAPIのHitomi API利用時および監視スクリプト起動時に、旧JSONが存在すれば
`INSERT ... ON CONFLICT DO NOTHING` で全件を取り込む。1 transaction内で実行し、
途中失敗時は全件rollbackする。JSONは移行後も可搬バックアップとして残すが、
新規検出・既読更新の正本には使用しない。`hitomi_legacy_imports` に移行元パス・mtime・
サイズを記録し、JSONが変わっていない通常のAPIアクセスでは全件再走査を省略する。

---

## 5. ファイル構成

### 5.1. バックエンド

| パス | 役割 |
|---|---|
| `backend/tools/hitomi_monitor.py` | 監視 CLI のエントリ（Task Scheduler から起動） |
| `backend/tools/__init__.py` | パッケージマーカ |
| `backend/services/hitomi/__init__.py` | パッケージマーカ |
| `backend/services/hitomi/nozomi.py` | NOZOMI 取得・big-endian デコード |
| `backend/services/hitomi/metadata.py` | `/galleries/<id>.js` 取得・パース |
| `backend/services/hitomi/watchlist.py` | watchlist.json CRUD・作者名正規化 |
| `backend/services/hitomi/state_store.py` | state.json 操作 |
| `backend/services/hitomi/arrival_store.py` | meta2.db の検出履歴CRUD・旧JSON移行 |
| `backend/routers/hitomi.py` | `/api/hitomi/*` API（薄いラッパー） |
| `backend/tests/test_hitomi_nozomi.py` | NOZOMI パーサのユニットテスト |
| `backend/tests/test_hitomi_diff.py` | 差分検出ロジックのユニットテスト |
| `backend/tests/test_hitomi_watchlist.py` | 正規化ロジックのユニットテスト |

### 5.2. フロントエンド

| パス | 役割 |
|---|---|
| `frontend/src/pages/HitomiPage.tsx` | 新着一覧 + 監視対象管理の統合ページ（`/hitomi` ルート） |
| `frontend/src/components/hitomi/HitomiArrivalCard.tsx` | 新着カード単体 |
| `frontend/src/components/hitomi/HitomiWatchlistDialog.tsx` | 監視対象編集ダイアログ |
| `frontend/src/hooks/useHitomiArrivals.ts` | 新着一覧取得・dismiss・dismiss-all・run-now フック |
| `frontend/src/hooks/useHitomiWatchlist.ts` | 監視対象の取得・追加・削除フック |
| `frontend/src/types/hitomi.ts` | 型定義 |

### 5.3. データディレクトリ

```
backend/data/hitomi/         ← .gitignore 対象（個人データ）
├── watchlist.json
├── state.json
└── new_arrivals.json          ← 旧データ移行元。移行後は読み取り専用
```

検出履歴の正本は `$META_DB_DIR/meta2.db`。`backend/data/` は既に `.gitignore` 対象であり、
JSON・DBとも自動的に除外される。Linuxの日次DBバックアップには `meta2.db` として含まれる。

### 5.4. 依存追加

`backend/pyproject.toml` の `[project].dependencies` に **`httpx`** を追加（現状 dev のみ）。
追加コマンド: `cd backend && uv add httpx`

---

## 6. API 仕様

### 6.1. `GET /api/hitomi/new-arrivals`

新着または既読履歴と監視ジョブのヘルス情報を取得する。

**クエリ**:
- `status`: `unread`（既定）/ `read` / `all`
- `offset`: 0以上（既定0）
- `limit`: 1〜200（既定60）

**レスポンス**:
```json
{
  "items": [ {} ],
  "status": "unread",
  "total": 12,
  "unread_count": 12,
  "read_count": 308,
  "offset": 0,
  "limit": 60,
  "last_run_at": "2026-04-29T03:00:00+09:00",
  "last_run_status": "ok",
  "last_error": null
}
```

`items` は指定statusのものを検出日時の新しい順で返す。

### 6.2. `POST /api/hitomi/dismiss/{id}`

新着アイテムを既読化（`is_read=1`, `read_at=<JST>`）。行は削除しない。

**レスポンス**: `{"message": "Dismissed", "id": 2034567}`

### 6.3. `POST /api/hitomi/dismiss-all`

全件を一括既読化。

**レスポンス**: `{"message": "All dismissed", "dismissed_count": 12}`

### 6.4. `GET /api/hitomi/watchlist`

監視対象の作者一覧を取得する。

**レスポンス**:
```json
{
  "artists": [
    { "display_name": "aka shio", "normalized": "aka_shio", "language": "japanese", "added_at": "2026-04-29" }
  ]
}
```

### 6.5. `POST /api/hitomi/watchlist`

監視対象の作者を追加する。バックエンドで `display_name` を正規化し、NOZOMI URL の存在確認を行う。

**リクエストボディ**:
```json
{ "display_name": "aka shio", "language": "japanese" }
```

**レスポンス**: `{"message": "Added", "normalized": "aka_shio"}`

**エラー**:
- `400`: 重複登録 / 不正な文字
- `404`: 正規化後の NOZOMI URL が 404（hitomi.la に作者が存在しない）

**登録時の既存作品除外（初回新着スキップ）**:

watchlist への追加直後、NOZOMI 先頭 1 件を取得して `state.json` の `artists[key].top_id` を
初期化する。これにより初回監視実行時に `diff_unseen_ids()` が「登録前に既に存在していた作品」を
新着と誤検出しなくなる。

- NOZOMI 取得が失敗した場合（ネットワーク障害等）はエラーログを記録するが、登録自体は成功扱いで返す。この場合は初回監視時に全件が新着として出現することがある
- 取得した NOZOMI の件数が 0（作者に作品なし）の場合は top_id を初期化しない（= 次の監視で全件が新着になる）

### 6.6. `DELETE /api/hitomi/watchlist/{normalized}`

監視対象を削除（state.json の該当エントリも削除）。

**レスポンス**: `{"message": "Removed"}`

### 6.7. `POST /api/hitomi/run-now`

監視スクリプト (`tools.hitomi_monitor.main`) を **同期実行** する。Task Scheduler を
待たずに即座に新着確認したい場合のためのエンドポイント。

実行中は他の `run-now` リクエストを 409 Conflict で拒否（モジュール内 `threading.Lock`
で排他制御）。完了後はクライアントが `GET /api/hitomi/new-arrivals` を再取得する想定。

**クエリパラメータ**:
- `force` (オプション、default `false`) — `true` を指定すると全作者を強制再チェック。
  `false`（デフォルト）の場合、当日 0:00（ローカルタイム）以降に `checked_at` が
  記録されている作者をスキップする。Task Scheduler からの直接実行（CLI）には
  適用されず、本 API 経由のみの挙動

**レスポンス**:
```json
{
  "exit_code": 0,
  "last_run_at": "2026-04-29T...",
  "last_run_status": "ok",
  "last_error": null,
  "last_run_stats": {
    "added": 3,
    "skipped": 2,
    "errors": 0
  }
}
```

- `exit_code`: 0 = 全成功 / 1 = 部分失敗 / 2 = 致命的失敗
- `last_run_stats.added`: 今回の実行で `meta2.db.hitomi_arrivals` に追加された件数
- `last_run_stats.skipped`: 当日 0:00 以降のチェック済み判定により今回スキップされた作者数
- `last_run_stats.errors`: NOZOMI / メタデータ取得で失敗した件数

**エラー**:
- `409`: 既に実行中
- `500`: 致命的失敗（state.json が壊れている等）

**設計判断:**

UI から手動取得する場合、ユーザーが連打したり、watchlist の修正のたびに毎回
全作者を再チェックすると hitomi.la への無駄な負荷になる。当日 0:00 以降に取得済みの
作者はスキップするデフォルトを設けることで、1 日 1 回までに頻度アクセスを抑制する。
0:00 を境に判定がリセットされるため、日付が変われば再度 1 回フェッチできる。
Task Scheduler 経由（CLI 直接実行）はこのスキップを適用しないため、定期監視は
これまで通り動作する。

**注意点**:
- 監視作者が多い・新着が多い初回実行では数十秒かかる場合があるため、フロントエンドは
  HTTP タイムアウトを 120 秒に伸ばしてリクエストする
- API としては blocking なので長時間処理用 UI（spinner / disable）を出す

---

## 7. クラス・関数設計

### 7.1. `services/hitomi/nozomi.py`

```python
def fetch_nozomi_head(
    artist_normalized: str,
    language: str = "japanese",
    count: int = 20,
    *,
    client: httpx.Client | None = None,
) -> list[int]:
    """
    NOZOMI ファイル先頭 N 件の ID を取得する。
    Range リクエストで count*4 バイトのみ取得し、big-endian 32bit int をデコード。
    """
```

- 404 時: `HitomiArtistNotFoundError`
- ネットワークエラー時: `HitomiNetworkError`

### 7.2. `services/hitomi/metadata.py`

```python
def fetch_metadata(gallery_id: int, *, client: httpx.Client | None = None) -> dict:
    """
    /galleries/<id>.js を取得し、`var galleryinfo = {...};` の右辺 JSON をパース。
    主要フィールド: id, title, artists[], language, type, date, files[]
    """
```

### 7.3. `services/hitomi/watchlist.py`

```python
def normalize_artist_name(display_name: str) -> str:
    """内部識別子（state.json キー）を生成する。URL 構築には別途 build_nozomi_url を使う。

    'AKA SHIO' → 'aka_shio'
    'aka shio' → 'aka_shio'
    """
    return display_name.strip().lower().replace(' ', '_')

def load_watchlist() -> list[WatchlistEntry]: ...
def add_artist(display_name: str, language: str) -> WatchlistEntry: ...  # 重複 / NOZOMI 存在を検証
def remove_artist(normalized: str) -> None: ...
```

### 7.4. `services/hitomi/state_store.py`

```python
def load_state() -> State: ...
def save_state(state: State) -> None: ...
```

`new_arrivals.json` のCRUDと30日purgeは廃止し、state.jsonだけを担当する。

### 7.5. `services/hitomi/arrival_store.py`

```python
def import_legacy_json(data_dir: Path) -> int: ...
def merge_new_items(items: list[ArrivalItem]) -> int: ...
def list_arrivals(status: ArrivalStatus, offset: int, limit: int) -> ArrivalPage: ...
def dismiss(gallery_id: int) -> bool: ...
def dismiss_all() -> int: ...
```

全関数は `services.meta_db.db_connection()` の短命接続を使う。旧JSON移行と追加は
gallery_id主キーで冪等、更新系はtransactionでcommit/rollbackする。

### 7.6. `tools/hitomi_monitor.py`

```python
def main() -> int:
    """
    終了コード:
      0: 全成功
      1: 部分失敗（一部作者で例外）
      2: 致命的失敗（state.json 読み書き失敗等）
    """
```

監視1回につき `httpx.Client` を1つだけ生成し、NOZOMI取得と全ギャラリーのメタデータ取得へ明示的に渡す。HTTP keep-aliveとコネクションプールを作者・ギャラリー間で再利用し、終了時はcontext managerで必ずcloseする。サービス関数を単独利用した場合だけ内部で一時Clientを所有する。

1 作者で例外発生 → 握りつぶして次へ進む。`state["last_error"]` に集約。

### 7.7. `routers/hitomi.py`

state_store / watchlist サービスを呼ぶだけの薄いラッパー。FastAPI の DI で `get_dirs_by_source()` のような既存パターンに揃える必要はない（独立データのため）。

### 7.8. `hooks/useHitomiArrivals.ts` / `hooks/useHitomiWatchlist.ts`

責務を 2 フックに分割して実装。

```typescript
function useHitomiArrivals(status: 'unread' | 'read') {
  return {
    items: ArrivalItem[],
    total: number,
    unreadCount: number,
    readCount: number,
    lastRunAt: string | null,
    lastRunStatus: 'ok' | 'partial' | 'error' | 'never',
    dismiss: (id: number) => Promise<void>,    // unread時の楽観的更新 + サーバ反映
    dismissAll: () => Promise<void>,           // unreadのみ
    runNow: () => Promise<void>,               // 同期実行（完了後に自動 refresh）
    refresh: () => Promise<void>,              // マウント時 + 手動 only（ポーリング無し）
  }
}

function useHitomiWatchlist() {
  return {
    artists: WatchlistEntry[],
    addArtist: (displayName: string, language: string) => Promise<void>,
    removeArtist: (normalized: string, language: string) => Promise<void>,
    refresh: () => Promise<void>,
  }
}
```

---

## 8. NOZOMI 仕様メモ（将来の仕様変更検知のため）

### 8.1. URL パターン

```
https://ltn.gold-usergeneratedcontent.net/n/artist/<artist_url>-<language>.nozomi
```

- `<artist_url>`: 内部 key（`_` 区切り）を **空白に戻してから URL encode** した値。
    - 例: 内部 key `aka_shio` → URL `aka%20shio`
    - 例: 内部 key `山田_花子` → URL `%E5%B1%B1%E7%94%B0%20%E8%8A%B1%E5%AD%90`
- `<language>`: `japanese` / `english` 等

### 8.1.1. 内部 key と URL の使い分け（重要）

hitomi.la の **NOZOMI ファイル名は実際には空白を含む**（`aka shio-japanese.nozomi`）。内部 key で
`_` を使うのは Pic2PDF_Viewer 側の都合（state.json キーの可読性・OS パスとの相性）であり、
hitomi.la のファイル名仕様とは別物である。

| レイヤ | 例 | 仕様 |
|---|---|---|
| ユーザー入力 (UI) | `"AKA SHIO"` / `"aka shio"` / `"aka_shio"` | 自由（半角空白と `_` は同義として受け入れる） |
| 内部 key (`state.json` キー / 重複検出) | `aka_shio` | `lowercase + 空白→_` |
| NOZOMI URL | `aka%20shio` | key の `_` を空白に戻して URL encode |

URL 構築は `services/hitomi/nozomi.build_nozomi_url(artist_key, language)` に集約する。

### 8.2. ファイル構造

| 項目 | 値 |
|---|---|
| 形式 | バイナリ |
| 1 要素 | 4 バイト（32bit 整数） |
| エンディアン | **big-endian** |
| 順序 | 新着順（先頭が最新） |
| 全長 | 該当条件のギャラリー数 × 4 バイト |

`hitomi.la` の `searchlib.js` で `DataView.getInt32(offset, false)` を使っている（false = big-endian）ため確定。

### 8.3. メタデータエンドポイント

```
https://ltn.gold-usergeneratedcontent.net/galleries/<gallery_id>.js
```

JS ファイル冒頭に `var galleryinfo = {...};` の形式で JSON が埋め込まれている。プレフィックスを除去して `JSON.parse` する。

---

## 10. 運用（Linux systemd timer）

systemd ユニットファイルは `deploy/hitomi-monitor.service` / `deploy/hitomi-monitor.timer` に格納。
`deploy_to_linux.sh` でサーバーへ転送される。

### 10.1. 初回登録（SSH 接続後に一度だけ実行）

```bash
ssh amashio@medaroserver

# ユニットファイルをコピー
sudo cp /opt/pic2pdf-viewer/deploy/hitomi-monitor.service /etc/systemd/system/
sudo cp /opt/pic2pdf-viewer/deploy/hitomi-monitor.timer   /etc/systemd/system/

# 有効化・起動
sudo systemctl daemon-reload
sudo systemctl enable --now hitomi-monitor.timer

# 登録確認
systemctl list-timers hitomi-monitor.timer
```

### 10.2. 動作確認（手動実行）

```bash
# タイマーを待たず今すぐ実行
sudo systemctl start hitomi-monitor.service

# ログ確認
tail -f /opt/pic2pdf-viewer/logs/hitomi-monitor.log
```

### 10.3. ユニットファイル更新後の反映

`deploy_to_linux.sh` 実行後、SSH でリロードする。

```bash
sudo systemctl daemon-reload
sudo systemctl restart hitomi-monitor.timer
```

### 10.4. ヘルス確認

```bash
# タイマー次回実行時刻・最終実行の確認
systemctl list-timers hitomi-monitor.timer

# 最新ログ
tail -50 /opt/pic2pdf-viewer/logs/hitomi-monitor.log
```

- バックエンドの新着画面に「最終実行: YYYY-MM-DD HH:MM / ステータス: ok」と表示される
- `last_run_status: error` が続く場合は NOZOMI URL の仕様変更を疑う（§8 を参照して再検証）

## 11. Discord 通知（実行結果）

監視 1 回ごとに新着件数を Discord に通知するオプション機能。**新着 0 件でも送信**する（正常稼働の生存確認を兼ねる）。

### 11.1. 有効化

環境変数 `HITOMI_DISCORD_WEBHOOK_URL` に Discord チャンネルの Webhook URL を設定する（`.env`）。未設定なら通知は完全に no-op。

- Windows / Mac: プロジェクトルート `.env`
- Linux systemd: `EnvironmentFile=/opt/pic2pdf-viewer/.env`（`deploy/hitomi-monitor.service`）経由で同じ `.env` を参照

### 11.2. 対象トリガーと差し込み位置

`tools/hitomi_monitor.py` の `main()` 末尾（`last_run_stats` 確定後）で `services/hitomi/notify.notify_run_result()` を呼ぶ。手動 API（`POST /hitomi/run-now`）・systemd 定期・Task Scheduler は全て `main()` を通るため、この 1 箇所で全経路をカバーする。watchlist が空の早期 return 経路でも同様に送信する。

### 11.3. 送信内容と失敗時の挙動

- 本文: `📥 hitomi 新着監視: 新着 N 件（skip M / エラー K）`（件数のみ）
- 送信は `httpx.post` で Webhook に `{"content": ...}` を POST
- **通知失敗は監視処理を止めない**。`httpx.HTTPError` は握りつぶし stderr に warning を出すのみ（`last_run_status` には影響しない）

---

## 11. リスク・注意事項

| リスク | 対応 |
|---|---|
| NOZOMI URL / 形式の変更 | `last_run_status` で検知、UI に状態表示。再解析の起点として §8 を残す |
| 大量の新着で NOZOMI 取得が不足 | 先頭 20 件だけだと取りこぼす可能性。週次なら問題ないが、間隔が空く場合は count を増やす |
| 履歴DBの破損・消失 | `meta2.db` の日次Online Backup・整合性検査・週次復元試験に含める |
| 作者名の特殊文字 | `build_nozomi_url` で URL encode するが、エッジケースは UI バリデーションで弾く |
| ToS 観点 | 個人用途・低頻度・低帯域なら現実的に問題ないと考えるが、再配布や商用利用は想定外 |
| メタデータ取得失敗 | 個別 ID で例外を握りつぶし、他に影響させない。state に error 集約 |

---

実装計画（Phase 1-4）・設計判断の経緯は [凍結記録](../../../archive/hitomi監視_実装計画と設計判断.md) を参照。
