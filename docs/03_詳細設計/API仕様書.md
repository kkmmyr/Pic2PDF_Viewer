# API仕様書

バックエンド (FastAPI) が提供するAPIエンドポイントの仕様。

---

## PDFライブラリ・ファイル操作

### `GET /api/pdfs`
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
  "directories": ["subdir1", "subdir2"],
  "current_path": "path/to/current"
}
```
- `created_at`: ファイルの作成日時（Unix タイムスタンプ、秒）

---

### `GET /api/books/{path}/images`
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

### `POST /api/pdfs/{filename}/delete_pages`
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

### `POST /api/directories`
フォルダを作成する。

**リクエストボディ**:
```json
{
  "path": "current/relative/path",
  "name": "new_folder_name",
  "source": "generated"
}
```

**レスポンス**: `{"message": "Directory created"}`

---

### `POST /api/move`
ファイル・フォルダを移動する。

**リクエストボディ**:
```json
{
  "items": ["file1.pdf", "subfolder"],
  "source_path": "current/relative/path",
  "destination_path": "dest/relative/path",
  "source": "generated"
}
```

**レスポンス**:
```json
{ "message": "Items moved", "moved_count": 2, "errors": [] }
```
- `errors`: 個別アイテムのエラーメッセージリスト（成功時は空配列）

---

### `PATCH /api/rename`
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

### `POST /api/thumbnails/regenerate_bulk`
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

### `POST /api/pdfs/merge`
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

### `POST /api/thumbnails/regenerate`
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

## 書籍メタデータ

### `POST /api/meta/auto-fill`
指定ソースの書籍に対してサークル名自動登録ジョブを開始する。

**クエリパラメータ**:
- `source` (オプション) — `generated`(default) / `kindle` / `novel`
- `mode` (オプション、default: `unknown_only`) — 処理対象の絞り込み条件
  - `missing_only`: 作者名エントリが未登録の書籍のみ処理
  - `unknown_only`: 「作者不明」または未登録の書籍を処理（デフォルト）
  - `overwrite_all`: 全件を上書き処理

**レスポンス**: `{"started": true, "source": "generated", "mode": "unknown_only"}`

**エラー**:
- `400`: 既にジョブが実行中 / 不正な `mode` 値

---

### `GET /api/meta/auto-fill/status`
自動登録ジョブの進捗を取得する。クライアントは 1500ms 間隔でポーリングする。

**クエリパラメータ**:
- `source` (オプション) — `generated`(default) / `kindle` / `novel`

**レスポンス**:
```json
{
  "status": "running",
  "total": 15,
  "done": 3,
  "skipped": 264,
  "current": "book_title",
  "results": [{"title": "book_title", "author": "作者A"}],
  "error": ""
}
```
- `status` の値: `idle` / `running` / `done` / `error`
- `total`: 処理対象件数（スキップ分を除く）
- `skipped`: 対象外としてスキップした件数

---

### `GET /api/meta/auto-fill/test`
1件分の自動登録をデバッグ実行する。ジョブを起動せず同期的に、各ステップ（DLsite/Fanza 直接検索 / 汎用クエリへのフォールバック / Gemma 抽出結果）の中間状態を返す。SearXNG・Gemma の挙動確認用。

**クエリパラメータ**:
- `title` — テスト対象の書籍タイトル
- `source` (オプション) — `generated`(default) / `kindle` / `novel`

**レスポンス例** (generated ソース):
```json
{
  "title": "サンプルタイトル",
  "source": "generated",
  "direct_query": "サンプルタイトル site:dmm.co.jp OR site:dlsite.com",
  "direct_searxng_hit": true,
  "direct_searxng_snippets": "...検索結果スニペット先頭500文字...",
  "direct_gemma_raw": "サークル名候補",
  "direct_result": "サークル名候補",
  "final": "サークル名候補",
  "used_fallback": false
}
```

汎用クエリへフォールバックする場合は加えて `query` / `extract_target` / `searxng_hit` / `searxng_snippets` / `gemma_raw` フィールドが含まれる。

---

### `GET /api/meta`
指定ソースの書籍メタデータを全件取得する。各エントリは作者名・タグ・閲覧回数・最終閲覧時刻を含む。

**クエリパラメータ**:
- `source` (オプション) — `generated`(default) / `kindle` / `novel`

**レスポンス例**:
```json
{
  "book.pdf": {
    "authors": ["作者A"],
    "tags": ["ジャンル1", "気分A"],
    "view_count": 5,
    "last_viewed_at": 1714200000.0
  },
  "subdir/another.pdf": {
    "authors": ["作者A", "作者B"]
  }
}
```
- キー: `"{path}/{filename}"` または `"{filename}"`（path が空の場合）
- `tags` / `view_count` / `last_viewed_at` は登録があった場合のみ含まれる。
- `last_viewed_at` は UNIX タイムスタンプ（秒、float）。

---

### `PATCH /api/meta`
1冊または複数冊の作者名・タグを上書き保存する。指定されたフィールドのみ更新し、他のフィールド（閲覧履歴等）は保持される。

**リクエストボディ**:
```json
{
  "path": "current/relative/path",
  "names": ["book1.pdf", "book2.pdf"],
  "authors": ["作者A", "作者B"],
  "tags": ["ジャンル1"],
  "source": "generated"
}
```
- `names` — 更新対象のファイル名リスト（複数指定で一括更新）
- `authors` — 上書きする作者名リスト（**省略時は変更しない**）
- `tags` — 上書きするタグリスト（**省略時は変更しない**）
- `authors` と `tags` のどちらかは指定が必要。

**マージ規則** (`authors` と `tags` で同じ):
- 非空配列を渡した場合: 該当フィールドのみ上書き。他フィールド（`view_count` / `last_viewed_at` / もう一方のリスト）は保持。
- 空配列 (`[]`) を渡した場合: 該当フィールドを「空配列のまま残す」。ただしエントリ全体に他フィールドが何もなければエントリ自体を削除。
- 省略した場合 (`undefined`): 該当フィールドは変更しない。

**レスポンス**: `{"message": "Updated", "updated_count": 2}`

---

### `POST /api/meta/view`
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
  "incremented": true
}
```
- `incremented`: 連打抑制によりカウントが据え置かれた場合は `false`、+1 した場合は `true`。

**用途**: ライブラリ画面で書籍カードをクリックした瞬間にフロントエンドが呼び出す。「最近見た順」ソート (`recent_view`) と「よく見る順」ソート (`view_desc`) のためのデータを蓄積する。

---

## シリーズ管理

### `POST /api/series/resolve`
シリーズ自動グループ化ジョブを起動する。指定ソースの書籍を走査し、ルールベース（タイトル前方一致 + 作者完全一致 + 巻数パターン）で同シリーズと判定されたエントリに `series_id` / `series_title` / `series_index` を書き戻す。

**クエリパラメータ**:
- `source` (オプション) — `generated`(default) / `kindle` / `novel`

**レスポンス**: `{"started": true, "source": "generated"}`

**エラー**:
- `400`: 不正な source
- `409`: 既にジョブが実行中

---

### `GET /api/series/resolve/status`
シリーズ判定ジョブの進捗を返す。

**クエリパラメータ**:
- `source` (オプション) — `generated`(default) / `kindle` / `novel`

**レスポンス**:
```json
{
  "status": "running",
  "total": 120,
  "done": 50,
  "created": 8,
  "current": "鬼滅の刃",
  "error": ""
}
```
- `status` の値: `idle` / `running` / `done` / `error`
- `total`: 走査対象書籍数
- `done`: 走査済み件数
- `created`: 作成された（または更新された）シリーズ数

---

## PDF生成

### `POST /api/generate`
指定ディレクトリ内の画像からPDFを生成する。

**リクエストボディ**:
```json
{
  "source_dir": "C:\\Absolute\\Path\\To\\Images",
  "generate_compressed": false,
  "quality": 50
}
```
- `generate_compressed` (オプション, bool) — `true` の場合、圧縮版PDFを `pdfs_compressed/` にも同時生成
- `quality` (オプション, int 1〜95) — 圧縮品質。`generate_compressed: true` の場合のみ使用

**レスポンス**:
```json
{
  "job_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "status": "pending"
}
```
- ジョブは非同期で実行される。進捗・結果は `GET /api/generate/job/{job_id}` でポーリングして取得する。

---

### `GET /api/generate/job/{job_id}`
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
  "message": "",
  "error": null
}
```
- `status` の値: `pending` / `running` / `completed` / `failed`
- `current_item`: 現在処理中のアイテム名（未処理時は `null`）
- `files`: 完了時に生成されたファイル名リスト
- `message`: 完了・失敗時のサマリーメッセージ
- `error`: 失敗時のエラーメッセージ

---

### `GET /api/status`
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

### `POST /api/batch_compress`
`data/main/images/` 配下の全WebP画像を一括で圧縮PDFに変換する。既存ファイルはスキップ。

**リクエストボディ**:
```json
{ "quality": 50 }
```

**レスポンス**: `{"message": "Batch compression complete", "files": [...]}`

---

## OCR

### `POST /api/ocr/run`
Novel用OCR処理 (`batch_ocr.py`) を開始する。

**クエリパラメータ**:
- `target_dir` (オプション) — 対象ディレクトリを指定（省略時は全未処理フォルダ）

---

### `POST /api/ocr/stop`
実行中のOCRプロセスを停止する。

---

### `GET /api/ocr/status`
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
