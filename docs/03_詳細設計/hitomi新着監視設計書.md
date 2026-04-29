# hitomi.la 新着監視設計書

特定作者の新着ギャラリーを定期監視して、ライブラリ画面から確認・hitomi.la へのリンクで遷移できる機能の設計書。本機能は **既存の Pic2PDF_Viewer 本体機能とは独立** しており、設計上も実行プロセスとしても疎結合に組む。本機能に関する仕様・実装・運用はすべて本ファイルに集約する。

最終更新: 2026-04-29（登録時の既存作品除外を追加）

---

## 1. 機能概要

### 1.1. 目的

hitomi.la に登録された特定作者の **新着ギャラリーを自動的に検出**し、ユーザーが Pic2PDF_Viewer のライブラリ画面で一覧確認・hitomi.la へ直接リンクで飛べるようにする。

### 1.2. 主な動作

- ユーザーが UI から作者を **監視リスト** に登録
- バックグラウンドのスクリプトが週次（任意間隔）で監視リストを巡回し、新着 ID を検出
- 検出した新着のメタデータ（タイトル・ページ数・公開日等）を取得して保存
- ユーザーは UI の「新着」リンクから一覧を見て、`hitomi.la/galleries/<id>.html` を新規タブで開く
- 既読化操作で個別 / 一括非表示。30 日経過で物理削除
- UI から「今すぐ取得」ボタンで Task Scheduler を待たずに監視スクリプトを手動実行できる（同期処理）

### 1.3. 制約・前提

- **NOZOMI は hitomi.la の内部仕様**であり、公式 API ではない。予告なく URL や形式が変わる可能性があるため、ヘルス情報を必ず記録し UI から状態確認できるようにする
- バックエンドサーバの常駐は **不要**（使うときだけ起動する運用を維持）
- 本機能のデータ（監視履歴・新着リスト）は個人視聴履歴に近く、**リポジトリには含めない**（`.gitignore` 対象）
- 通知（メール・Discord 等）は **対象外**。UI 表示のみ

---

## 2. アーキテクチャ

### 2.1. 全体構成

```
┌─ Windows Task Scheduler (週1回 起動)
│
└→ [hitomi_monitor.py]  ← 単発実行・終了
      │
      ├─ watchlist.json 読込
      ├─ NOZOMI 取得 (Range 数十バイト)
      ├─ 差分検出
      ├─ /galleries/<id>.js でメタデータ取得
      └─ new_arrivals.json / state.json に書き出し

[FastAPI] ──(JSON ファイル読込のみ)──→ [新着画面 React]
                                       └→ hitomi.la/<id>.html へリンク
```

### 2.2. 設計判断（Why）

- **既存 FastAPI に組み込まない理由:**
    - 監視を動かすにはバックエンド常駐が必要 → 個人用の起動運用と相性が悪い
    - ポーリング側でリソースリーク・ハングが起きると Web 全体に波及する
    - 1 回の監視はミリ秒で完了する単発タスクで、cron 的実行と相性が極めて良い
- **JSON ファイル経由で連携する理由:**
    - プロセス間 IPC 不要、最小コスト
    - スクリプトとバックエンドのライフサイクルが完全独立（片方が死んでも片方は動く）
    - state ファイルのバージョン管理 / バックアップが容易

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
    e. new_arrivals.json に追加（重複は無視）
    f. state.json の top_id を更新
[4] dismissed=true かつ discovered_at が 30 日以前のエントリを物理削除
[5] state.json に last_run_at / last_run_status を記録
[6] 終了
```

UI 側は GET `/api/hitomi/new-arrivals` で `new_arrivals.json` を読み、画面に表示するだけ。

---

## 4. データ構造（JSON 形式）

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

### 4.3. `new_arrivals.json`

```json
{
  "items": [
    {
      "id": 2034567,
      "artist": "aka_shio",
      "display_artist": "aka shio",
      "title": "...",
      "language": "japanese",
      "type": "manga",
      "page_count": 24,
      "published_at": "2026-04-28T...",
      "discovered_at": "2026-04-29T03:00:00+09:00",
      "url": "https://hitomi.la/galleries/2034567.html",
      "dismissed": false
    }
  ]
}
```

`dismissed: true` のアイテムも 30 日間は残る（再 POLL で蒸し返さないため）。

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
| `backend/services/hitomi/state_store.py` | state.json / new_arrivals.json 操作・30日 purge |
| `backend/routers/hitomi.py` | `/api/hitomi/*` API（薄いラッパー） |
| `backend/tests/test_hitomi_nozomi.py` | NOZOMI パーサのユニットテスト |
| `backend/tests/test_hitomi_diff.py` | 差分検出ロジックのユニットテスト |
| `backend/tests/test_hitomi_watchlist.py` | 正規化ロジックのユニットテスト |

### 5.2. フロントエンド

| パス | 役割 |
|---|---|
| `frontend/src/components/hitomi/HitomiNewArrivalsPage.tsx` | 新着一覧画面 |
| `frontend/src/components/hitomi/HitomiWatchlistDialog.tsx` | 監視対象編集ダイアログ |
| `frontend/src/components/hitomi/HitomiArrivalCard.tsx` | 新着カード単体 |
| `frontend/src/hooks/useHitomiArrivals.ts` | 一覧取得・dismiss・watchlist CRUD フック |
| `frontend/src/types/hitomi.ts` | 型定義 |

### 5.3. データディレクトリ

```
backend/data/hitomi/         ← .gitignore 対象（個人データ）
├── watchlist.json
├── state.json
└── new_arrivals.json
```

`backend/data/` は既に `.gitignore` 対象であり、自動的に除外される。

### 5.4. 依存追加

`backend/pyproject.toml` の `[project].dependencies` に **`httpx`** を追加（現状 dev のみ）。
追加コマンド: `cd backend && uv add httpx`

---

## 6. API 仕様

### 6.1. `GET /api/hitomi/new-arrivals`

保留中の新着一覧と監視ジョブのヘルス情報を取得する。

**レスポンス**:
```json
{
  "items": [ {} ],
  "last_run_at": "2026-04-29T03:00:00+09:00",
  "last_run_status": "ok",
  "last_error": null
}
```

`items` は `dismissed=false` のもののみ、新着順。

### 6.2. `POST /api/hitomi/dismiss/{id}`

新着アイテムを既読化（dismissed=true）。

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
- `skip_recent_days` (オプション、default `3.0`) — 指定日数以内に `checked_at` が
  記録されている作者をスキップする。`0` を指定すると全作者を強制再チェック。
  Task Scheduler からの直接実行（CLI）には適用されず、本 API 経由のみの挙動

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
- `last_run_stats.added`: 今回の実行で `new_arrivals.json` に追加された件数
- `last_run_stats.skipped`: `skip_recent_days` により今回スキップされた作者数
- `last_run_stats.errors`: NOZOMI / メタデータ取得で失敗した件数

**エラー**:
- `409`: 既に実行中
- `500`: 致命的失敗（state.json が壊れている等）

**設計判断:**

UI から手動取得する場合、ユーザーが連打したり、watchlist の修正のたびに毎回
全作者を再チェックすると hitomi.la への無駄な負荷になる。直近 3 日以内に取得済みの
作者はスキップするデフォルトを設けることで、想定外の頻度アクセスを抑制する。
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
def fetch_metadata(gallery_id: int) -> dict:
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
def load_arrivals() -> Arrivals: ...
def save_arrivals(arrivals: Arrivals) -> None: ...
def merge_new_items(items: list[ArrivalItem]) -> int:
    """new_arrivals.json に追加。重複（同 id）は無視。追加件数を返す。"""
def dismiss(gallery_id: int) -> None: ...
def purge_expired(threshold_days: int = 30) -> int:
    """dismissed=true かつ discovered_at が threshold_days 以前のエントリを物理削除。削除件数を返す。"""
```

### 7.5. `tools/hitomi_monitor.py`

```python
def main() -> int:
    """
    終了コード:
      0: 全成功
      1: 部分失敗（一部作者で例外）
      2: 致命的失敗（state.json 読み書き失敗等）
    """
```

1 作者で例外発生 → 握りつぶして次へ進む。`state["last_error"]` に集約。

### 7.6. `routers/hitomi.py`

state_store / watchlist サービスを呼ぶだけの薄いラッパー。FastAPI の DI で `get_dirs_by_source()` のような既存パターンに揃える必要はない（独立データのため）。

### 7.7. `hooks/useHitomiArrivals.ts`

```typescript
function useHitomiArrivals() {
  return {
    items: ArrivalItem[],
    lastRunAt: string | null,
    lastRunStatus: 'ok' | 'partial' | 'error' | 'never',
    dismiss: (id: number) => Promise<void>,    // 楽観的更新 + サーバ反映
    dismissAll: () => Promise<void>,
    refresh: () => Promise<void>,              // マウント時 + 手動 only（ポーリング無し）
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

### 8.1.2. なぜ `_` で URL を組むと 404 になるか

検索ページの URL（`hitomi.la/search.html?artist:aka_shio`）では `_` が空白の代わりに使われる
ため、**初見では NOZOMI URL も `_` 区切りに見える**が、実際には NOZOMI ファイル名は空白を
そのまま含む別ストレージ。Phase 1 着手時にこの違いを誤認し、`/n/artist/aka_shio-japanese.nozomi`
（`_` 区切り）で 404 を踏んだ。正しくは `/n/artist/aka%20shio-japanese.nozomi`（空白を URL encode）。

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

## 9. Phase 別実装計画

### 進捗概観（2026-04-29 時点）

| Phase | ステータス | コミット | 補足 |
|---|---|---|---|
| Phase 1 | ✅ 完了（運用化待ち） | `18aec89` + `f61e9c0` | サービス層 + 監視 CLI + ユニットテスト |
| Phase 2 | ✅ 完了 | `f3d5fff` | 閲覧 API + 新着一覧 UI |
| Phase 3 | ✅ 完了 | `ef557bf` | watchlist 編集 UI + 規約整合 |
| 拡張: 「今すぐ取得」 | ✅ 完了 | `dd4801b` | UI から同期実行ボタン |
| 拡張: 直近 3 日スキップ | ✅ 完了 | `5fa45f3` | 過剰アクセス抑制 + 実行統計 |
| 拡張: 登録時 top_id 初期化 | ✅ 完了 | — | 登録前の既存作品を新着として誤検出しない |
| Phase 4: 表紙画像 | ⏸ **スキップ確定** | — | 実装コスト > 利益。`hitomi.la で開く` リンクで代替 |

**Phase 1 の運用化に必要な残タスク:** Task Scheduler 登録（§10.2）+ 1 週間動作観察。

### Phase 1: 監視スクリプト単体（UI なし） ✅

1. `backend/services/hitomi/nozomi.py` + 単体テスト
2. `backend/services/hitomi/metadata.py` + 単体テスト
3. `backend/services/hitomi/state_store.py` + 単体テスト
4. `backend/services/hitomi/watchlist.py` + 単体テスト
5. `backend/tools/hitomi_monitor.py`
6. `backend/data/hitomi/watchlist.json` を手動で作成し `aka_shio` を登録
7. `uv run python -m tools.hitomi_monitor` で動作確認
8. Task Scheduler 登録（→ §10）
9. 1 週間動かして `state.json` / `new_arrivals.json` の正常性を確認

**完了条件:** 新着 ID が `new_arrivals.json` に蓄積される

### Phase 2: 閲覧 UI ✅

1. `backend/routers/hitomi.py`（new-arrivals / dismiss / dismiss-all）
2. `frontend/src/types/hitomi.ts`
3. `frontend/src/hooks/useHitomiArrivals.ts`
4. `frontend/src/components/hitomi/HitomiArrivalCard.tsx`
5. `frontend/src/components/hitomi/HitomiNewArrivalsPage.tsx`
6. ヘッダーに「新着」リンクとバッジを追加

**完了条件:** ブラウザから新着確認 + 既読化が可能

### Phase 3: 監視対象管理 UI ✅

1. `backend/routers/hitomi.py` に watchlist CRUD 追加
2. `useHitomiArrivals.ts` に `addWatchlist` / `removeWatchlist` 追加
3. `HitomiWatchlistDialog.tsx`
4. 不正な作者名のバリデーション（NOZOMI 404 即時試験）

**完了条件:** UI から作者の追加・削除が可能

### Phase 4（任意）: 表紙画像表示 ⏸ スキップ確定

検討の結果、**実装コストが利益を上回るためスキップ判定**。理由:

1. **実装コスト**: hitomi.la の `gg.js` 画像 URL ハッシュ生成ロジックを移植する必要が
   あり、彼らの仕様変更で容易に壊れる。CORS / Referer 制約からバックエンド画像
   プロキシ + ローカルキャッシュの設計も必要となり、機能 1 つ分のコストが大きい
2. **利益が小さい**: カードに表紙画像が出るだけで、既に「hitomi.la で開く」ボタン
   から 1 クリックで原本の表紙含めて閲覧可能
3. **負荷観点**: ブラウザキャッシュ（`Cache-Control: max-age=31536000`）が効く前提
   なら実際の hitomi.la への負荷は誤差レベルだが、本機能の方針として `hitomi.la`
   への直リンクで完結させることに合致

**再検討トリガー**: 「どうしてもカード上で表紙を確認したい」運用シーンが出た時点で
本セクションを更新して着手する。

参考実装メモ（着手時の起点として残す）:
1. `https://ltn.gold-usergeneratedcontent.net/common.js` + `gg.js` から `gg.b()` /
   `gg.s()` 関数を読解しサブドメインハッシュアルゴリズムを移植
2. 画像 URL は概ね `https://<subdomain>.gold-usergeneratedcontent.net/webp/<hash>/<id>.webp`
3. CORS / Referer ヘッダ制約を確認し、必要なら `GET /api/hitomi/cover/{id}` の
   バックエンドプロキシ + `backend/data/hitomi/covers/<id>.webp` ローカルキャッシュ

---

## 10. 運用（Task Scheduler 登録）

### 10.1. 動作確認（初回）

```powershell
cd D:\61.tool\Pic2PDF_Viewer\backend
uv run python -m tools.hitomi_monitor
```

正常終了するとコンソールに「監視完了: 新着 N 件、エラー 0 件」のような出力。`backend/data/hitomi/state.json` に `last_run_at` が記録される。

### 10.2. タスクスケジューラへの登録（週 1 回）

1. **タスクスケジューラ** → 「タスクの作成」
2. **全般** タブ
    - 名前: `Pic2PDF Hitomi Monitor`
    - 「ユーザーがログオンしているかどうかにかかわらず実行する」をチェック
3. **トリガー** タブ → 新規
    - 「毎週」、月曜 03:00 等
4. **操作** タブ → 新規
    - プログラム: `D:\61.tool\Pic2PDF_Viewer\backend\.venv\Scripts\python.exe`（`uv run` 経由でも可）
    - 引数: `-m tools.hitomi_monitor`
    - 開始 (作業フォルダ): `D:\61.tool\Pic2PDF_Viewer\backend`
5. **条件** タブ
    - 「コンピューターが AC 電源で動作している場合のみタスクを開始する」のチェックは任意
6. 保存後、右クリック「実行」で動作確認

### 10.3. ヘルス確認

- バックエンドの新着画面に「最終実行: YYYY-MM-DD HH:MM / ステータス: ok」と表示される
- 1 週間以上 `last_run_at` が更新されない場合、タスクスケジューラの履歴を確認
- `last_run_status: error` が続く場合は NOZOMI URL の仕様変更を疑う（§8 を参照して再検証）

---

## 11. リスク・注意事項

| リスク | 対応 |
|---|---|
| NOZOMI URL / 形式の変更 | `last_run_status` で検知、UI に状態表示。再解析の起点として §8 を残す |
| 大量の新着で NOZOMI 取得が不足 | 先頭 20 件だけだと取りこぼす可能性。週次なら問題ないが、間隔が空く場合は count を増やす |
| 作者名の特殊文字 | `build_nozomi_url` で URL encode するが、エッジケースは UI バリデーションで弾く |
| ToS 観点 | 個人用途・低頻度・低帯域なら現実的に問題ないと考えるが、再配布や商用利用は想定外 |
| メタデータ取得失敗 | 個別 ID で例外を握りつぶし、他に影響させない。state に error 集約 |
