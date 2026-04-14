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
    { "name": "file1.pdf", "thumbnail": "/thumbnails/path/to/file1.jpg" },
    { "name": "file2.pdf", "thumbnail": null }
  ],
  "directories": ["subdir1", "subdir2"],
  "current_path": "path/to/current"
}
```

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

**レスポンス**: 生成されたファイル名のリスト

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
