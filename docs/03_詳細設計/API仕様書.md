# API仕様書

バックエンド (FastAPI) が提供するAPIエンドポイントの仕様。

---

## 目次

- [§1. PDFライブラリ・ファイル操作](#1-pdfライブラリファイル操作)
  - §1.1 `GET /api/pdfs` — PDF / ディレクトリ一覧
  - §1.2 `GET /api/books/{path}/images` — 書籍の画像リスト
  - §1.3 `POST /api/pdfs/{filename}/delete_pages` — ページ削除
  - §1.4 `PATCH /api/rename` — ファイル / フォルダ名変更
  - §1.5 `DELETE /api/pdfs` — 非表示書籍の完全削除
  - §1.6 `GET /api/genres` — ジャンルリスト取得
  - §1.7 `POST /api/genres` — ジャンル追加
  - §1.8 `DELETE /api/genres/{name}` — ジャンル削除
  - §1.9 `PATCH /api/genres/reorder` — ジャンル並べ替え
  - §1.10 `POST /api/thumbnails/regenerate_bulk` — サムネイル一括再生成
  - §1.11 `POST /api/pdfs/merge` — PDF 結合
  - §1.12 `POST /api/thumbnails/regenerate` — サムネイル単体再生成
  - §1.13 `GET /api/thumbnails/page` — ページサムネイル
- [§2. 書籍メタデータ](#2-書籍メタデータ)
  - §2.4 `GET /api/meta` — メタデータ全件取得
  - §2.5 `GET /api/meta/export` — メタデータエクスポート
  - §2.6 `PATCH /api/meta` — メタデータ更新
  - §2.7 `POST /api/meta/view` — 閲覧記録
- [§3. シリーズ管理](#3-シリーズ管理)
  - §3.2 `POST /api/series/assign` — シリーズ割り当て
  - §3.3 `POST /api/series/unassign` — シリーズ解除
  - §3.4 `POST /api/series/reorder` — シリーズ内並べ替え
  - §3.7 `POST /api/series/suggest` — 既存シリーズへの紐付け候補提案（A-1）
- [§4. PDF生成](#4-pdf生成)
  - §4.1 `POST /api/generate` — PDF 生成ジョブ起動
  - §4.2 `GET /api/generate/job/{job_id}` — 生成ジョブ進捗
  - §4.3 `GET /api/status` — ソースディレクトリスキャン状況
  - §4.4 `POST /api/batch_compress` — 一括圧縮
- [§5. OCR](#5-ocr)
  - §5.1 `POST /api/ocr/run` — OCR 開始
  - §5.2 `POST /api/ocr/stop` — OCR 停止
  - §5.3 `GET /api/ocr/status` — OCR 状態
- [§6. hitomi.la 新着監視](#6-hitomila-新着監視)
  - §6.1 `GET /api/hitomi/new-arrivals` — 新着一覧
  - §6.2 `POST /api/hitomi/dismiss/{gallery_id}` — 既読化
  - §6.3 `POST /api/hitomi/dismiss-all` — 一括既読化
  - §6.4 `GET /api/hitomi/watchlist` — 監視対象作者一覧
  - §6.5 `POST /api/hitomi/watchlist` — 監視作者追加
  - §6.6 `DELETE /api/hitomi/watchlist/{normalized}` — 監視作者削除
  - §6.7 `POST /api/hitomi/run-now` — 監視即時実行

---

## §1. PDFライブラリ・ファイル操作

### §1.1 `GET /api/pdfs`
PDFファイルとディレクトリの一覧を取得する。

**クエリパラメータ**:
- `path` (オプション) — 表示するサブディレクトリの相対パス
- `source` (オプション) — `generated`(default) / `kindle` / `novel`

**レスポンス**:
```json
{
  "files": [
    { "name": "file1.pdf", "thumbnail": "/thumbnails/path/to/file1.jpg", "created_at": 1713200000.0 },
    { "name": "file2.pdf", "thumbnail": null, "created_at": 1713100000.0 }
  ],
  "current_path": "path/to/current"
}
```
- `created_at`: ファイルの作成日時（Unix タイムスタンプ、秒）

---

### §1.2 `GET /api/books/{path}/images`
指定された書籍（フォルダまたはZIP）の画像リストを取得する。

**パスパラメータ**:
- `path` — 書籍（フォルダまたはZIP）の相対パス

**クエリパラメータ**:
- `source` (オプション) — `generated`(default) / `kindle` / `novel`

**レスポンス**:
```json
{
  "images": [
    "/images/path/to/book/01.webp",
    "/images/path/to/book/02.webp"
  ]
}
```

---

### §1.3 `POST /api/pdfs/{filename}/delete_pages`
PDFの指定ページを削除する。

**クエリパラメータ**:
- `path` (オプション) — 対象ファイルの親ディレクトリ相対パス
- `source` (オプション) — `generated`(default) / `kindle` / `novel`

**リクエストボディ**:
```json
{ "page_indices": [0, 2, 5] }
```

**レスポンス**:
```json
{ "message": "Pages deleted successfully", "total_pages": 10 }
```

---

### §1.4 `PATCH /api/rename`
PDF ファイルまたはフォルダの名前を変更する。PDF の場合はサムネイル・画像ディレクトリも連動してリネームする。

**リクエストボディ**:
```json
{
  "path": "current/relative/path",
  "old_name": "old_name.pdf",
  "new_name": "new_name.pdf",
  "source": "generated",
  "is_folder": false
}
```
- `is_folder` — `true` の場合はフォルダとして処理（サムネイルフォルダ・画像フォルダも連動）

**レスポンス**: `{"message": "Item renamed", "new_name": "new_name.pdf"}`

**エラー**:
- `404`: 対象アイテムが存在しない
- `400`: 変更後の名前が既に存在する

---

### §1.5 `DELETE /api/pdfs`
非表示書籍をディスクから完全削除する（PDF・サムネイル・画像ディレクトリ・メタデータを削除）。

**リクエストボディ**:
```json
{
  "names": ["book1.pdf", "book2.pdf"],
  "path": "current/relative/path",
  "source": "generated"
}
```

**レスポンス**: `{"message": "Items deleted", "deleted_count": 2, "errors": []}`

**エラー**:
- `500`: 全件削除失敗（部分失敗の場合は 200 + errors 配列に詳細）

---

### §1.6 `GET /api/genres`
ソース別のジャンルリスト（表示順）を返す。ファイルが未作成の場合は meta.json から既存 `genre` フィールドを収集して初期リストを返す。

**クエリパラメータ**: `source=generated`（省略可）

**レスポンス**: `["オリジナル", "プリンセスコネクト", "Voiceloid"]`

---

### §1.7 `POST /api/genres`
ジャンルを追加する。

**リクエストボディ**: `{"source": "generated", "name": "新ジャンル"}`

**レスポンス**: `{"genres": ["オリジナル", "プリンセスコネクト", "Voiceloid", "新ジャンル"]}`

**エラー**: `409` 既に同名ジャンルが存在する

---

### §1.8 `DELETE /api/genres/{name}`
指定ジャンルをリストから削除する（既存書籍の `genre` フィールドは変更しない）。

**クエリパラメータ**: `source=generated`

**レスポンス**: `{"genres": ["オリジナル", "Voiceloid"]}`

**エラー**: `404` 指定ジャンルが存在しない

---

### §1.9 `PATCH /api/genres/reorder`
ジャンルの表示順を更新する。

**リクエストボディ**: `{"source": "generated", "genres": ["Voiceloid", "オリジナル", "プリンセスコネクト"]}`
- `genres` は既存ジャンルリストと同一集合である必要がある（増減不可）。

**レスポンス**: `{"genres": ["Voiceloid", "オリジナル", "プリンセスコネクト"]}`

---

### §1.10 `POST /api/thumbnails/regenerate_bulk`
選択した複数PDFのサムネイルを一括再生成する。

**リクエストボディ**:
```json
{
  "names": ["book1.pdf", "book2.pdf"],
  "path": "current/relative/path",
  "source": "generated"
}
```

**レスポンス**:
```json
{ "message": "Bulk thumbnail regeneration complete", "succeeded": ["book1.pdf"], "failed": [] }
```

---

### §1.11 `POST /api/pdfs/merge`
複数のPDFを順番に結合して新しいPDFを生成する。

**リクエストボディ**:
```json
{
  "names": ["book1.pdf", "book2.pdf"],
  "output_name": "merged.pdf",
  "path": "current/relative/path",
  "source": "generated"
}
```
- `names` — 結合対象のファイル名リスト（2件以上必須、順序通りに結合）
- `output_name` — 出力ファイル名（`.pdf` 拡張子必須、既存ファイル名と重複不可）

**レスポンス**:
```json
{ "message": "PDFs merged successfully", "output_name": "merged.pdf", "total_pages": 42 }
```

**エラー**:
- `400`: `names` が1件以下 / `output_name` に `.pdf` がない / 出力先に同名ファイルが存在する
- `404`: 結合対象PDFが存在しない

---

### §1.12 `POST /api/thumbnails/regenerate`
指定PDFのサムネイルを再生成する。

**リクエストボディ**:
```json
{
  "path": "current/relative/path",
  "name": "book.pdf",
  "source": "generated"
}
```

**レスポンス**: `{"message": "Thumbnail regenerated"}`

**エラー**:
- `404`: 対象PDFが存在しない
- `500`: サムネイル生成失敗

---

### §1.13 `GET /api/thumbnails/page`
指定ページのサムネイル画像をオンデマンドで返す。ページスライダーのドラッグ中プレビューに加え、**編集モードの全ページグリッドビュー**（`PageGridOverlay`）からも利用される。

ソースによって取得方法が異なる:
- `generated`: `images/{book}/` 配下の N 番目 WebP を直接返す（PDF 不要）
- `kindle` / `novel`: PDF を fitz でレンダリングして JPEG で返す

**クエリパラメータ**:

| パラメータ | 型 | 必須 | 説明 |
|---|---|---|---|
| `name` | string | ✓ | PDF ファイル名（.pdf 付き） |
| `page` | int | ✓ | ページ番号（1 始まり） |
| `path` | string | - | 相対パス（デフォルト `""`） |
| `source` | string | - | `generated` / `kindle` / `novel`（デフォルト `generated`） |
| `width` | int | - | 出力画像幅 px（`kindle`/`novel` のみ使用、デフォルト `400`） |

**レスポンス**:
- `generated`: `image/webp` バイナリ（`Cache-Control: max-age=3600`）
- `kindle`/`novel`: `image/jpeg` バイナリ（`Cache-Control: max-age=3600`）

**エラー**:
- `400`: `page < 1` またはページが範囲外
- `404`: 対象画像 / PDF が存在しない
- `500`: レンダリング失敗（`kindle`/`novel` のみ）

---

## §2. 書籍メタデータ

### §2.4 `GET /api/meta`
指定ソースの書籍メタデータを全件取得する。各エントリは作者名・閲覧回数・最終閲覧時刻・シリーズ情報・非表示フラグ・ジャンル・読書状態などを含む。

**クエリパラメータ**:
- `source` (オプション) — `generated`(default) / `kindle` / `novel`

**レスポンス例**:
```json
{
  "book.pdf": {
    "authors": ["作者A"],
    "view_count": 5,
    "last_viewed_at": 1714200000.0,
    "series_id": "abc12345",
    "series_title": "シリーズタイトル",
    "series_index": 1.5,
    "genre": "オリジナル",
    "read_state": "reading"
  },
  "subdir/another.pdf": {
    "authors": ["作者A", "作者B"],
    "hidden": true
  }
}
```
- キー: `"{path}/{filename}"` または `"{filename}"`（path が空の場合）
- すべての追加フィールド（`view_count` / `last_viewed_at` / `series_id` / `series_title` / `series_index` / `hidden` / `genre` / `read_state`）は登録があった場合のみ含まれる任意フィールド。
- `last_viewed_at` は UNIX タイムスタンプ（秒、float）。
- `series_index` は `float`（小数巻 `2.5` 等に対応）。
- `hidden=true` の書籍は通常モードでは UI 上非表示（API レスポンスには含まれる）。
- `read_state` は `'unread' | 'reading' | 'done'` のいずれか。**未設定の既存エントリは `view_count` から派生**（0 → unread / >0 → reading）するため、フロント側で「フィールド有無」を意識する必要はない。詳細は §2.6 / §2.7 / [詳細設計書_バックエンド編 §1.4 読書状態](詳細設計書_バックエンド編.md)。

---

### §2.5 `GET /api/meta/export`
指定ソースの書籍メタデータ全体を JSON ファイルとしてダウンロードする。バックアップ・環境移行用。

**クエリパラメータ**:
- `source` (オプション) — `generated`(default) / `kindle` / `novel`

**レスポンス**: `application/json` ファイル（`Content-Disposition: attachment; filename="meta_{source}_{YYYYMMDD}.json"`）  
ボディは `GET /api/meta` と同じ構造の JSON。

**用途**: ライブラリ画面「ツール」メニューの「メタデータをエクスポート」ボタンから起動。著者名・シリーズ・閲覧回数などの積み上げデータを保護する。

---

### §2.6 `PATCH /api/meta`
1冊または複数冊の作者名・非表示フラグ・ジャンル・読書状態を上書き保存する。指定されたフィールドのみ更新し、他のフィールド（閲覧履歴等）は保持される。

**リクエストボディ**:
```json
{
  "path": "current/relative/path",
  "names": ["book1.pdf", "book2.pdf"],
  "authors": ["作者A", "作者B"],
  "hidden": true,
  "genre": "オリジナル",
  "read_state": "done",
  "source": "generated"
}
```
- `names` — 更新対象のファイル名リスト（複数指定で一括更新）
- `authors` — 上書きする作者名リスト（**省略時は変更しない**）
- `hidden` — 非表示フラグ（**省略時は変更しない**、`true` で非表示化、`false` で再表示してフィールド削除）
- `genre` — ジャンル文字列（**省略時は変更しない**、空文字でフィールド削除）
- `read_state` — 読書状態 (`'unread' | 'reading' | 'done'`)。**省略時は変更しない**、空文字でフィールド削除（=`view_count` 由来の派生に戻す）
- `authors` / `hidden` / `genre` / `read_state` のいずれかは指定が必要。

**マージ規則**:
- `authors`:
    - 非空配列を渡した場合: フィールドのみ上書き。他フィールド（`view_count` / `last_viewed_at` / `hidden` 等）は保持。
    - 空配列 (`[]`) を渡した場合: フィールドを「空配列のまま残す」。エントリ全体に他フィールドが何もなければエントリ自体を削除。
- `hidden`:
    - `true`: フィールドを保存（非表示化）。
    - `false`: フィールドを削除（再表示）。
- `genre`:
    - 非空文字列: フィールドを上書き保存。
    - 空文字列 `""`: フィールドを削除。
- `read_state`:
    - `'unread'` / `'reading'` / `'done'`: フィールドを上書き保存。
    - 空文字列 `""`: フィールドを削除（以後は `view_count` 由来の派生で扱われる）。
    - 上記以外の文字列は 400。
- 省略した場合 (`undefined`): 該当フィールドは変更しない。

**レスポンス**: `{"message": "Updated", "updated_count": 2}`

---

### §2.7 `POST /api/meta/view`
書籍の閲覧を記録する。`last_viewed_at` は呼び出し毎に常に更新されるが、`view_count` は前回の閲覧から `VIEW_COUNT_DEBOUNCE_SEC = 300`（5分）以上経過した場合のみ +1 される（連打抑制）。`authors` 等の他フィールドは保持される。

**リクエストボディ**:
```json
{
  "path": "current/relative/path",
  "name": "book.pdf",
  "source": "generated"
}
```

**レスポンス**:
```json
{
  "view_count": 6,
  "last_viewed_at": 1714200300.5,
  "incremented": true,
  "read_state": "reading"
}
```
- `incremented`: 連打抑制によりカウントが据え置かれた場合は `false`、+1 した場合は `true`。
- `read_state`: 自動遷移後の読書状態。`incremented=true` のときに既存値が `done` でなければ `'reading'` に自動遷移する（連打抑制でカウントが据え置かれた場合は変更しない）。

**用途**: ライブラリ画面で書籍カードをクリックした瞬間にフロントエンドが呼び出す。「最近見た順」ソート (`recent_view`) と「よく見る順」ソート (`view_desc`) のためのデータを蓄積する。読書状態の自動遷移（unread → reading）もここで行う。最終ページ到達時の `done` 遷移は §2.6 `PATCH /api/meta` で行う。

---

## §3. シリーズ管理

### §3.2 `POST /api/series/assign`
書籍を既存または新規シリーズに割り当てる（手動編集用）。複数書籍を同時に同じシリーズへ追加できる。

**リクエストボディ**:
```json
{
  "path": "current/relative/path",
  "names": ["book1.pdf", "book2.pdf"],
  "title": "シリーズタイトル",
  "index": [4.0, 5.0],
  "id": "abc12345",
  "source": "generated"
}
```
- `names` — 対象ファイル名リスト（複数指定可）
- `title` — シリーズ表示名（必須）
- `index` — シリーズ内巻数（float）。**`number` または `number[]`**:
    - 単一 number → すべての `names` に同じ巻数を割り当て（単冊編集の従来挙動）
    - number 配列 → `names[i]` に `index[i]` を割り当て（複数選択からの一括登録用、長さは names と一致が必須）
- `id` — 既存シリーズに追加する場合の `series_id`。**省略時はバックエンドで生成**（`title` + 作者集合のハッシュ）。
- 他のメタフィールド（authors / view_count 等）は変更しない。

**レスポンス**: `{"message": "Assigned", "id": "abc12345", "updated_count": 2}`

**エラー**:
- `400`: `index` 配列の長さが `names` と一致しない

---

### §3.3 `POST /api/series/unassign`
書籍をシリーズから外す（series_id / series_title / series_index フィールドを削除する）。

**リクエストボディ**:
```json
{
  "path": "current/relative/path",
  "names": ["book1.pdf", "book2.pdf"],
  "source": "generated"
}
```

**レスポンス**: `{"message": "Unassigned", "updated_count": 2}`

---

### §3.4 `POST /api/series/reorder`
同じシリーズに属する書籍の `series_index` を **配列の順序どおり 1.0, 2.0, 3.0, ...** に振り直す（DnD 並べ替え用）。

**リクエストボディ**:
```json
{
  "path": "current/relative/path",
  "names": ["vol3.pdf", "vol1.pdf", "vol2.pdf"],
  "series_id": "abc12345",
  "source": "generated"
}
```
- `names` — シリーズに属する書籍を **新しい順序で** 並べたリスト
- `series_id` — 対象シリーズ。指定 `names` の `series_id` がすべて一致しないと 400
- 他のメタフィールド（authors / view_count 等）は変更しない

**レスポンス**: `{"message": "Reordered", "updated_count": 3}`

**エラー**:
- `400`: `names` が空 / `series_id` が一致しない書籍が含まれる

---

### §3.7 `POST /api/series/suggest`
選択された書籍に対して、**既存シリーズへの紐付け候補**を提案する（A-1）。書き込み副作用なしの読み取り専用エンドポイント。新規シリーズを発見するわけではなく、既に登録されているシリーズへの追加候補だけを返す。

**リクエストボディ**:
```json
{
  "path": "current/relative/path",
  "names": ["book1.pdf", "book2.pdf"],
  "source": "generated"
}
```

**レスポンス**:
```json
{
  "candidates": [
    {
      "series_id": "abc12345",
      "series_title": "鬼滅の刃",
      "series_max_index": 5.0,
      "score": 0.85,
      "reason": "title_match,author_match"
    },
    {
      "series_id": "def67890",
      "series_title": "炎柱外伝",
      "series_max_index": 2.0,
      "score": 0.62,
      "reason": "title_match"
    }
  ]
}
```

**マッチング戦略（ルールベース）**:
- 既存シリーズの `series_title` から末尾の巻数表記を除いた本体で比較
- 各選択書籍タイトルとの **共通プレフィックス長 / min(タイトル長, シリーズ本体長)** をスコア化
- 全選択書籍の **平均スコア** を採用（複数冊が同一シリーズに属するかを評価）
- 全書籍で作者集合が一致した場合のみ +0.2 加点（最大 1.0 にクランプ）
- スコア `0.4` 以上の上位 5 件を降順で返す

**エラー**:
- `400`: `names` が空 / 不正な source

**用途**: フロントエンドの「シリーズに一括登録」ダイアログ内に「AI が提案するシリーズに追加」モードを追加し、モード選択時に自動で本エンドポイントを呼び出して候補をラジオで表示する。ユーザー確認後、既存の `POST /api/series/assign` で書き込みを行う（自動実行はしない）。

---

## §4. PDF生成

### §4.1 `POST /api/generate`
指定ディレクトリ内の画像からPDFを生成する。生成された PDF は `backend/data/main/pdfs_compressed/` 配下に保存される（`/pdfs` 静的マウントから配信）。

**リクエストボディ**:
```json
{
  "source_dir": "C:\\Absolute\\Path\\To\\Images"
}
```
- 圧縮品質を指定したい場合は、生成後に `POST /api/batch_compress` を別途呼び出す（生成APIは品質パラメータを受け付けない）

**レスポンス**:
```json
{
  "job_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "status": "pending"
}
```
- ジョブは非同期で実行される。進捗・結果は `GET /api/generate/job/{job_id}` でポーリングして取得する。

---

### §4.2 `GET /api/generate/job/{job_id}`
非同期PDF生成ジョブの進捗・結果を取得する。クライアントは 1500ms 間隔でポーリングする。

**パスパラメータ**:
- `job_id` — `POST /api/generate` が返した UUID

**レスポンス**:
```json
{
  "job_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "status": "running",
  "current_item": "folder_name",
  "files": [],
  "failed_items": [],
  "message": "",
  "error": null
}
```
- `status` の値: `pending` / `running` / `completed` / `failed`
- `current_item`: 現在処理中のアイテム名（未処理時は `null`）
- `files`: 完了時に生成されたファイル名リスト
- `failed_items`: 完了時に書籍単位で失敗したものの一覧。`[{name: string, error: string}, ...]`。サイレント失敗を防ぎフロントで「○件失敗」と表示するために使用。
- `message`: 完了・失敗時のサマリーメッセージ。失敗があれば `"Generation complete: N succeeded, M failed"` の形式。
- `error`: ジョブ全体としての失敗メッセージ（書籍単位の失敗ではなく、ジョブ自体が `FAILED` になった場合）

---

### §4.3 `GET /api/status`
PDF生成処理の進捗状況を取得する。

**クエリパラメータ**:
- `source_dir` — スキャン対象のソースディレクトリ

**レスポンス**:
```json
{
  "items": [
    {"name": "folder_name", "type": "folder", "status": "not_started"},
    {"name": "zip_name",    "type": "zip",    "status": "completed"}
  ]
}
```
- `status` の値: `not_started` / `in_progress` / `completed`

---

### §4.4 `POST /api/batch_compress`
`data/main/images/` 配下の全WebP画像を一括で圧縮PDFに変換する。既存ファイルはスキップ。

**リクエストボディ**:
```json
{ "quality": 50 }
```

**レスポンス**: `{"message": "Batch compression complete", "files": [...]}`

---

## §5. OCR

### §5.1 `POST /api/ocr/run`
Novel用OCR処理 (`batch_ocr.py`) を開始する。

**クエリパラメータ**:
- `target_dir` (オプション) — 対象ディレクトリを指定（省略時は全未処理フォルダ）

---

### §5.2 `POST /api/ocr/stop`
実行中のOCRプロセスを停止する。

---

### §5.3 `GET /api/ocr/status`
現在のOCRプロセスのステータスとログを取得する。

**レスポンス**:
```json
{
  "status": "idle",
  "logs": ["[INFO] Processing..."],
  "last_return_code": null
}
```
- `status` の値: `idle` / `running` / `error`

---

## §6. hitomi.la 新着監視

詳細設計: [hitomi新着監視設計書.md §6](hitomi新着監視設計書.md#6-api-仕様)

### §6.1 `GET /api/hitomi/new-arrivals`

未既読の新着ギャラリー一覧と監視ジョブのヘルス情報を取得する。

**レスポンス**:
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
  ],
  "last_run_at": "2026-04-29T03:00:00+09:00",
  "last_run_status": "ok",
  "last_error": null
}
```
- `items`: `dismissed=false` のもののみ、新着順
- `last_run_status` の値: `ok` / `partial` / `error` / `never`

---

### §6.2 `POST /api/hitomi/dismiss/{gallery_id}`

新着アイテムを既読化（`dismissed=true`）する。

**パスパラメータ**:
- `gallery_id` — ギャラリー ID（整数）

**レスポンス**: `{"message": "Dismissed", "id": 2034567}`

**エラー**:
- `404`: 指定 ID が存在しない

---

### §6.3 `POST /api/hitomi/dismiss-all`

未読の全アイテムを一括既読化する。

**レスポンス**: `{"message": "All dismissed", "dismissed_count": 12}`

---

### §6.4 `GET /api/hitomi/watchlist`

監視対象の作者一覧を取得する。

**レスポンス**:
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

---

### §6.5 `POST /api/hitomi/watchlist`

監視対象の作者を追加する。NOZOMI URL の存在確認を行い、登録時に `state.json` の `top_id` を初期化する（既存作品の誤検出防止）。

**リクエストボディ**:
```json
{ "display_name": "aka shio", "language": "japanese" }
```

**レスポンス**: `{"message": "Added", "normalized": "aka_shio"}`

**エラー**:
- `400`: 重複登録 / 不正な文字
- `404`: hitomi.la に作者が存在しない（NOZOMI 404）

---

### §6.6 `DELETE /api/hitomi/watchlist/{normalized}`

監視対象を削除する。`state.json` の該当エントリも削除する。

**パスパラメータ**:
- `normalized` — 内部識別子（`aka_shio` 形式）

**クエリパラメータ**:
- `language` (オプション、default `japanese`)

**レスポンス**: `{"message": "Removed"}`

**エラー**:
- `404`: 指定 normalized が存在しない

---

### §6.7 `POST /api/hitomi/run-now`

監視スクリプトを同期実行する（Task Scheduler を待たず即時取得）。実行中の二重起動は 409 で拒否。

**クエリパラメータ**:
- `skip_recent_days` (オプション、default `3.0`) — 指定日数以内に確認済みの作者をスキップ。`0` で全作者強制再チェック

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
- `exit_code`: `0` = 全成功 / `1` = 部分失敗 / `2` = 致命的失敗

**エラー**:
- `409`: 既に実行中
