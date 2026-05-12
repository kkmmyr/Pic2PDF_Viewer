# API仕様書

バックエンド (FastAPI) が提供するAPIエンドポイントの仕様。

---

## 目次

- [§1. PDFライブラリ・ファイル操作](#1-pdfライブラリファイル操作)
  - §1.1 `GET /api/pdfs` — PDF / ディレクトリ一覧
  - §1.2 `GET /api/books/{path}/images` — 書籍の画像リスト
  - §1.3 `POST /api/pdfs/{filename}/delete_pages` — ページ削除
  - §1.3.1 `POST /api/pdfs/{filename}/reorder_pages` — ページ並び替え
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
- [§7. 小説テキスト検索・RAG（novel_db）](#7-小説テキスト検索ragnovel_db)
  - §7.1 `GET /api/novel_db/books` — 書籍一覧 + DB 状態
  - §7.2 `GET /api/novel_db/series` — novel シリーズ一覧
  - §7.3 `POST /api/novel_db/search` — ハイブリッド検索（FTS5 + ベクトル + RRF）
  - §7.4 `POST /api/novel_db/qa` — RAG 質問応答（SSE）
  - §7.5 `GET /api/novel_db/qa/history` — 履歴一覧
  - §7.6 `GET /api/novel_db/qa/history/{id}` — 履歴詳細
  - §7.7 `DELETE /api/novel_db/qa/history/{id}` — 履歴削除
  - §7.8 `POST /api/novel_db/rebuild` — 再構築ジョブ起動
  - §7.9 `GET /api/novel_db/rebuild/status` — ジョブキュー状態
  - §7.10 `DELETE /api/novel_db/rebuild/{job_id}` — 待機中ジョブのキャンセル

---

## §1. PDFライブラリ・ファイル操作

### §1.1 `GET /api/pdfs`
PDFファイルとディレクトリの一覧を取得する。

**クエリパラメータ**:
- `path` (オプション) — 表示するサブディレクトリの相対パス
- `source` (オプション) — `doujin`(default) / `comic` / `novel`

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
- `source` (オプション) — `doujin`(default) / `comic` / `novel`

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
書籍の指定ページを削除する。ソースによって動作が異なる:

- **`doujin`**: image-only モード。`images/{book_name}/` 配下の WebP を natsort 順に並べて、N 番目を削除する（ファイルが残った WebP の natsort 順に「ページ N」が再マッピングされる）。表紙サムネイルは削除後の先頭 WebP から PIL ベースで再生成。
- **`comic` / `novel`**: PDF モード。fitz で PDF を開いて該当ページを削除し、上書き保存。表紙サムネイルは削除後の PDF 先頭ページから fitz ベースで再生成。

**クエリパラメータ**:
- `path` (オプション) — 対象ファイルの親ディレクトリ相対パス
- `source` (オプション) — `doujin`(default) / `comic` / `novel`

**リクエストボディ**:
```json
{ "page_indices": [0, 2, 5] }
```

**レスポンス**:
```json
{ "message": "Pages deleted successfully", "total_pages": 10 }
```

**エラー**:
- `404`: 対象書籍が見つからない（doujin は `images/{book_name}/` ディレクトリ不在、comic/novel は PDF 不在）
- `400`: ページインデックス範囲外
- `400`: パストラバーサル拒否

---

### §1.3.1 `POST /api/pdfs/{filename}/reorder_pages`
書籍のページ順序を入れ替える。`page_indices[i]` は「新しい位置 `i` に配置する元ページの 0 始まりインデックス」を表す。`page_indices` は `[0..N-1]` の **完全なパーミュテーション** であること（重複・欠落は 400）。

ソースによって動作が異なる:

- **`doujin`**: `images/{book_name}/` 配下の WebP を natsort 順に並べ、`page_indices` の指す順で `page_0001.webp` / `page_0002.webp` / ... という採番に物理リネーム。一時名（`__reorder_tmp_*`）経由で 2 段階リネームを行い、衝突を回避する。表紙サムネイルは並び替え後の先頭 WebP から PIL ベースで再生成。
- **`comic` / `novel`**: fitz の `Document.select(page_indices)` で PDF を再構築して上書き保存。表紙サムネイルは fitz ベースで再生成。

**クエリパラメータ**:
- `path` (オプション) — 対象ファイルの親ディレクトリ相対パス
- `source` (オプション) — `doujin`(default) / `comic` / `novel`

**リクエストボディ**:
```json
{ "page_indices": [2, 0, 1, 3, 4] }
```
↑ 元の 5 ページを「元 page 3 → 新 page 1」「元 page 1 → 新 page 2」「元 page 2 → 新 page 3」… の順に並び替える。

**レスポンス**:
```json
{ "message": "Pages reordered successfully", "total_pages": 5 }
```

**エラー**:
- `404`: 対象書籍が見つからない
- `400`: `page_indices` が `[0..N-1]` のパーミュテーションでない（重複・範囲外・欠落）
- `400`: パストラバーサル拒否

---

### §1.4 `PATCH /api/rename`
PDF ファイルまたはフォルダの名前を変更する。PDF の場合はサムネイル・画像ディレクトリも連動してリネームする。

**リクエストボディ**:
```json
{
  "path": "current/relative/path",
  "old_name": "old_name.pdf",
  "new_name": "new_name.pdf",
  "source": "doujin",
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
  "source": "doujin"
}
```

**レスポンス**: `{"message": "Items deleted", "deleted_count": 2, "errors": []}`

**エラー**:
- `500`: 全件削除失敗（部分失敗の場合は 200 + errors 配列に詳細）

---

### §1.6 `GET /api/genres`
ソース別のジャンルリスト（表示順）を返す。ファイルが未作成の場合は meta.json から既存 `genre` フィールドを収集して初期リストを返す。

**クエリパラメータ**: `source=doujin`（省略可）

**レスポンス**: `["オリジナル", "プリンセスコネクト", "Voiceloid"]`

---

### §1.7 `POST /api/genres`
ジャンルを追加する。

**リクエストボディ**: `{"source": "doujin", "name": "新ジャンル"}`

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

**リクエストボディ**: `{"source": "doujin", "genres": ["Voiceloid", "オリジナル", "プリンセスコネクト"]}`
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
  "source": "doujin"
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
  "source": "doujin"
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
  "source": "doujin"
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
- `doujin`: `images/{book}/` 配下の N 番目 WebP を直接返す（PDF 不要）
- `comic` / `novel`: PDF を fitz でレンダリングして JPEG で返す

**クエリパラメータ**:

| パラメータ | 型 | 必須 | 説明 |
|---|---|---|---|
| `name` | string | ✓ | PDF ファイル名（.pdf 付き） |
| `page` | int | ✓ | ページ番号（1 始まり） |
| `path` | string | - | 相対パス（デフォルト `""`） |
| `source` | string | - | `doujin` / `comic` / `novel`（デフォルト `doujin`） |
| `width` | int | - | 出力画像幅 px（`comic`/`novel` のみ使用、デフォルト `400`） |

**レスポンス**:
- `doujin`: `image/webp` バイナリ（`Cache-Control: max-age=3600`）
- `comic`/`novel`: `image/jpeg` バイナリ（`Cache-Control: max-age=3600`）

**エラー**:
- `400`: `page < 1` またはページが範囲外
- `404`: 対象画像 / PDF が存在しない
- `500`: レンダリング失敗（`comic`/`novel` のみ）

---

## §2. 書籍メタデータ

### §2.4 `GET /api/meta`
指定ソースの書籍メタデータを全件取得する。各エントリは作者名・閲覧回数・最終閲覧時刻・シリーズ情報・非表示フラグ・ジャンル・読書状態などを含む。

**クエリパラメータ**:
- `source` (オプション) — `doujin`(default) / `comic` / `novel`

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
- `source` (オプション) — `doujin`(default) / `comic` / `novel`

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
  "source": "doujin"
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
  "source": "doujin"
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
  "source": "doujin"
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
  "source": "doujin"
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
  "source": "doujin"
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
  "source": "doujin"
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

---

## §7. 小説テキスト検索・RAG（novel_db）

novel タブのテキスト DB ビューア機能。設計の詳細は [小説テキスト検索・RAG機能_バックエンド設計.md](小説テキスト検索・RAG機能_バックエンド設計.md)、要件は [小説テキスト検索・RAG機能.md](../01_要件定義/小説テキスト検索・RAG機能.md) を参照。

### 共通仕様

- すべてのエンドポイントは `prefix=/api/novel_db`、`tags=["novel_db"]` で登録
- **再構築ジョブ実行中の検索 / 質問**: `503 Service Unavailable` を `Retry-After: 10` ヘッダ付きで返す（[バックエンド設計 §8.2](小説テキスト検索・RAG機能_バックエンド設計.md)）
- **共通エラーレスポンス**: `{"detail": "<message>"}` 形式（FastAPI 標準）
- **スコープオブジェクト** (`Scope`): 検索 / 質問 / 履歴 で共通の構造
    ```json
    { "type": "all" }                               // 全件
    { "type": "series", "id": "oko-kishi" }         // シリーズ単位
    { "type": "book", "name": "おこぼれ姫と..." }     // 単冊
    ```
    シリーズ未所属書籍は `type=series` の選択肢に含めない（[要件定義 TBD-7](../01_要件定義/小説テキスト検索・RAG機能.md)）。

---

### §7.1 `GET /api/novel_db/books`

novel ソースに登録された書籍一覧と DB 状態を返す。`data/kindle_novel/pdfs/` 配下の PDF を起点とし、`data/meta/novel/meta.json` の作者・シリーズ情報と `novel.db` の DB 状態を結合。

**クエリパラメータ**: なし

**レスポンス**:
```json
[
  {
    "name": "おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)",
    "authors": ["田中啓子"],
    "series_id": "oko-kishi",
    "series_name": "おこぼれ姫と円卓の騎士",
    "is_indexed": true,
    "page_count": 118,
    "indexed_at": "2026-05-09T11:30:00Z",
    "thumbnail_url": "/kindle_novel/images/おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)/001.png"
  }
]
```

- `is_indexed=false` のとき、`page_count` / `indexed_at` は `null`
- `series_id` / `series_name` はシリーズ未所属の場合 `null`
- `thumbnail_url` は連番 `001.png` をそのまま縮小表示用に返す（事前生成しない）

---

### §7.2 `GET /api/novel_db/series`

novel ソースのシリーズ一覧。書籍が 1 件以上紐付いているシリーズのみ返す（未所属書籍は §7.1 で取得）。

**レスポンス**:
```json
[
  { "id": "oko-kishi", "name": "おこぼれ姫と円卓の騎士", "book_count": 11 }
]
```

---

### §7.3 `POST /api/novel_db/search`

ハイブリッド検索（FTS5 OR + ベクトル検索 + RRF 融合）。

**リクエストボディ**:
```json
{
  "query": "デューク",
  "scope": { "type": "all" },
  "offset": 0,
  "limit": 20
}
```

| フィールド | 必須 | デフォルト | 説明 |
|---|---|---|---|
| `query` | ○ | — | 検索クエリ（自然文 / キーワードどちらでも可、長さ 1-200 字） |
| `scope` | ○ | — | スコープオブジェクト |
| `offset` | × | 0 | スキップ件数（無限スクロール用） |
| `limit` | × | 20 | 取得上限（最大 50） |

**レスポンス**:
```json
{
  "hits": [
    {
      "book_name": "おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)",
      "page_no": 50,
      "snippet": "…そう、俺は<mark>デューク</mark>。お前の…",
      "has_highlight": true,
      "image_url": "/kindle_novel/images/おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)/050.png",
      "rrf_score": 0.0312
    }
  ],
  "total": 42,
  "offset": 0,
  "limit": 20
}
```

- `snippet` は `<mark>` タグのみ許可（バックエンドで HTML エスケープ済み、フロントは `dangerouslySetInnerHTML` で安全に描画可能、[バックエンド設計 §6.3.1](小説テキスト検索・RAG機能_バックエンド設計.md)）
- `has_highlight=false` の場合は FTS5 ヒットなし、ベクトル検索のみのチャンク先頭 200 字（HTML エスケープのみ）
- `image_url` は `null` 可（元画像が無い場合）

**エラー**:
- `422`: `query` が空 / 200 字超 / `scope` が不正
- `503`: 再構築ジョブ実行中（`Retry-After: 10`）

---

### §7.4 `POST /api/novel_db/qa`（SSE）

ハイブリッド検索 → Gemma で質問応答。Server-Sent Events でトークンを逐次配信。

**Content-Type**: リクエスト `application/json` / レスポンス `text/event-stream`

**リクエストボディ**:
```json
{
  "question": "デュークはどのような人物ですか?",
  "scope": { "type": "all" }
}
```

| フィールド | 必須 | 説明 |
|---|---|---|
| `question` | ○ | 質問文（1-500 字） |
| `scope` | ○ | スコープオブジェクト |

**レスポンス（イベントストリーム）**:

```
data: {"token": "デュ"}

data: {"token": "ーク"}

data: {"token": "は"}

…

data: {"done": true, "history_id": 42, "eval_count": 1240, "done_reason": "stop"}
```

- `token` イベント: 生成された 1 単位（モデル依存、概ね数文字 〜 数十文字）
- `done` イベント: 生成完了。`history_id` は `qa_history` テーブルに保存された履歴 ID
- `done_reason`: `"stop"`（自然終了） / `"length"`（num_predict に達した） / `"canceled"`（クライアント切断）
- クライアントが接続切断（`AbortController.abort()`）した場合、サーバ側で `done_reason='canceled'` として途中までの応答を `qa_history.answer` に保存（[バックエンド設計 §7.6](小説テキスト検索・RAG機能_バックエンド設計.md)）

**エラー**:
- `422`: `question` が空 / 500 字超 / `scope` 不正
- `503`: 再構築ジョブ実行中（`Retry-After: 10`、SSE 確立前に通常 HTTP レスポンスで返す）

---

### §7.5 `GET /api/novel_db/qa/history`

質問履歴一覧（時系列降順）。各エントリは要約のみ。詳細は §7.6。

**クエリパラメータ**:
- `offset` (default `0`)
- `limit` (default `20`、最大 100)

**レスポンス**:
```json
{
  "items": [
    {
      "id": 42,
      "asked_at": "2026-05-09T11:45:00Z",
      "finished_at": "2026-05-09T11:46:30Z",
      "scope": { "type": "all" },
      "question": "デュークはどのような人物ですか?",
      "answer_preview": "デュークはレティの騎士であり、ナイツオブラウンドの第一席として…",
      "done_reason": "stop"
    }
  ],
  "total": 50
}
```

- `answer_preview`: `answer` の先頭 120 字 + `…`（hung up 時は途中まで）
- `done_reason='canceled'` のエントリも履歴に含まれる

---

### §7.6 `GET /api/novel_db/qa/history/{id}`

履歴詳細（プロンプト全文 / コンテキスト / モデル設定 / 応答メタを含む）。チューニング材料として全項目を保持（[要件定義 TBD-2](../01_要件定義/小説テキスト検索・RAG機能.md)）。

**レスポンス**:
```json
{
  "id": 42,
  "asked_at": "2026-05-09T11:45:00Z",
  "finished_at": "2026-05-09T11:46:30Z",
  "scope": { "type": "all" },
  "question": "デュークはどのような人物ですか?",
  "answer": "デュークはレティの騎士であり…",
  "prompt": "以下は小説『…』からの抜粋です。…",
  "context": [
    {
      "book_name": "おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)",
      "page_no": 50,
      "chunk_idx": 1,
      "score": 0.0312,
      "text": "そう、俺は殿下の騎士。…"
    }
  ],
  "model": "qwen3.6:35b-a3b",
  "options": {
    "temperature": 0.2,
    "repeat_penalty": 1.2,
    "num_predict": 4096,
    "num_ctx": 8192,
    "think": false
  },
  "eval_count": 1240,
  "done_reason": "stop",
  "error_message": null
}
```

**エラー**:
- `404`: 該当 `id` の履歴なし

---

### §7.7 `DELETE /api/novel_db/qa/history/{id}`

履歴 1 件を削除。

**レスポンス**: `204 No Content`

**エラー**:
- `404`: 該当 `id` の履歴なし

---

### §7.8 `POST /api/novel_db/rebuild`

再構築ジョブをキューに登録。即座に `job_id` を返し、worker スレッドが順次処理する（[バックエンド設計 §8](小説テキスト検索・RAG機能_バックエンド設計.md)）。

**リクエストボディ**:
```json
{
  "type": "book",
  "target_id": "おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)",
  "mode": "pdf_text"
}
```

| フィールド | 必須 | 値 / デフォルト | 説明 |
|---|---|---|---|
| `type` | ○ | `"book"` / `"series"` / `"all"` | ジョブ単位 |
| `target_id` | △ | — | `type='book'` のとき書籍名、`type='series'` のときシリーズ ID。`type='all'` では省略 |
| `mode` | × | `"pdf_text"` (default) / `"reocr"` | `pdf_text` = 既存 PDF テキスト層から抽出、`reocr` = 元画像から yomitoku 再 OCR（将来機能、現状未実装） |

**レスポンス**:
```json
{
  "job_id": 7,
  "queued_position": 1
}
```

- `queued_position`: キュー内の順番（1 = 次に実行）

**エラー**:
- `422`: 不正な `type` / `target_id` 不一致 / `mode='reocr'` を未実装段階で指定

---

### §7.9 `GET /api/novel_db/rebuild/status`

現在のジョブキュー状態を返す。フロントは 5 秒間隔でポーリング（[フロントエンド設計 §6.6](小説テキスト検索・RAG機能_フロントエンド設計.md)）。

**レスポンス**:
```json
{
  "is_running": true,
  "current_job": {
    "id": 7,
    "type": "all",
    "target_id": null,
    "mode": "pdf_text",
    "started_at": "2026-05-09T11:50:00Z",
    "progress_total": 11,
    "progress_done": 4
  },
  "queued_jobs": [
    {
      "id": 8,
      "type": "book",
      "target_id": "おこぼれ姫と円卓の騎士 2 女王の条件 (ビーズログ文庫)",
      "mode": "pdf_text",
      "enqueued_at": "2026-05-09T11:55:00Z"
    }
  ],
  "recent_finished": [
    {
      "id": 6,
      "type": "book",
      "target_id": "おこぼれ姫と円卓の騎士 3 (ビーズログ文庫)",
      "state": "completed",
      "finished_at": "2026-05-09T11:48:00Z"
    }
  ]
}
```

- `is_running=false` のとき `current_job` は `null`
- `recent_finished` は直近 5 件（`completed` / `failed` / `canceled` を含む）

---

### §7.10 `DELETE /api/novel_db/rebuild/{job_id}`

待機中ジョブをキャンセル（`state='canceled'` に更新）。

**レスポンス**: `204 No Content`

**エラー**:
- `404`: 該当 `job_id` なし
- `409`: ジョブが実行中（実行中ジョブはキャンセル不可、[バックエンド設計 §8.4](小説テキスト検索・RAG機能_バックエンド設計.md)）

---

### §7.11 `GET /api/novel_db/books/{book_name}/characters`（B-15）

書籍に登録済みのキャラ一覧を返す。`book_characters` テーブルが空（CLI 未実行）の書籍は `200 []` を返す。生成は `scripts/build_character_summaries.py` で行う（[バックエンド設計 §5.10](小説テキスト検索・RAG機能_バックエンド設計.md)）。

**ソート順**: `page_count` 降順 → `first_page` 昇順 → `name` 昇順

**レスポンス**:
```json
[
  {
    "name": "レティ",
    "first_page": 11,
    "page_count": 95,
    "has_summary": true
  },
  {
    "name": "デューク",
    "first_page": 8,
    "page_count": 69,
    "has_summary": true
  }
]
```

**エラー**:
- `404`: 該当書籍が `books` テーブルに無い

---

### §7.12 `GET /api/novel_db/books/{book_name}/characters/{char_name}`（B-15）

書籍 × キャラの詳細（人物像サマリ + 主要シーン top 5）を返す。

**`top_scenes`**: 当該キャラが `main_characters` に含まれる page を `char_count` 降順で上位 5 件。各要素は `{page_no, char_count}`。フロントは `page_no` を `PageImageModal` 表示にリンクする。

**レスポンス**:
```json
{
  "name": "レティ",
  "first_page": 11,
  "page_count": 95,
  "summary": "物語の第三王女について第一王女、レティーツィア…",
  "generated_at": "2026-05-11 22:21:37",
  "top_scenes": [
    { "page_no": 67, "char_count": 1820 },
    { "page_no": 92, "char_count": 1640 }
  ]
}
```

**エラー**:
- `404`: 該当書籍が無い、または該当キャラが `book_characters` に登録されていない

---

### §7.13 `GET /api/novel_db/qa/sessions`（B-16）

マルチターン会話 QA のセッション一覧。`last_message_at` 降順 → `started_at` 降順。

**クエリパラメータ**: `offset`（既定 0）/ `limit`（既定 20、最大 100）

**レスポンス**:
```json
[
  {
    "id": 12,
    "scope_type": "book",
    "scope_id": "おこぼれ姫と円卓の騎士 1",
    "title": "レティの内面はどう変化したか？",
    "started_at": "2026-05-12 09:00:00",
    "last_message_at": "2026-05-12 09:10:30",
    "message_count": 6
  }
]
```

---

### §7.14 `GET /api/novel_db/qa/sessions/{session_id}`（B-16）

セッション詳細（メッセージ全件含む）。`system` ロールのメッセージは LLM 投入用なので **レスポンスから除外**（UI には表示しない）。

**レスポンス**:
```json
{
  "id": 12,
  "scope_type": "book",
  "scope_id": "おこぼれ姫と円卓の騎士 1",
  "title": "レティの内面はどう変化したか？",
  "started_at": "2026-05-12 09:00:00",
  "last_message_at": "2026-05-12 09:10:30",
  "messages": [
    { "id": 21, "role": "user", "content": "レティの内面はどう変化したか？",
      "eval_count": null, "done_reason": null, "created_at": "..." },
    { "id": 22, "role": "assistant", "content": "page 67 ...",
      "eval_count": 432, "done_reason": "stop", "created_at": "..." }
  ]
}
```

**エラー**: `404` セッション無し

---

### §7.15 `POST /api/novel_db/qa/sessions`（B-16、SSE）

会話セッションを新規作成し、初手の質問を SSE で配信する。

**リクエストボディ**:
```json
{
  "scope": { "type": "book", "id": "おこぼれ姫と円卓の騎士 1" },
  "question": "レティの内面はどう変化したか？"
}
```

scope と question から system メッセージ（page 抜粋 + 俯瞰サマリ + 回答ルール）を組み立て、`(system, user)` の 2 メッセージを `qa_messages` に append したうえで LLM ストリーミングを開始する。

**SSE イベント形式（[バックエンド設計 §5.12](小説テキスト検索・RAG機能_バックエンド設計.md)）**:
- `data: {"token": "..."}` — 部分トークン
- `data: {"done": true, "session_id": 12, "message_id": 22, "eval_count": 432, "done_reason": "stop"}` — 終端
- `data: {"error": "..."}` — 失敗（バックエンド非対応含む）

**エラー**: `503` 再構築ジョブ実行中

---

### §7.16 `POST /api/novel_db/qa/sessions/{session_id}/messages`（B-16、SSE）

既存セッションに新ターンを追加する。

**リクエストボディ**:
```json
{ "question": "そのきっかけは何だった？" }
```

過去メッセージ（system + user/assistant 履歴）を全件読み込み、新 user メッセージを append したうえで LLM に投入する。SSE 形式は §7.15 と同じ。

**エラー**:
- `404` セッション無し
- `503` 再構築ジョブ実行中

---

### §7.17 `DELETE /api/novel_db/qa/sessions/{session_id}`（B-16）

セッションを削除（`qa_messages` も CASCADE で連動削除）。

**レスポンス**: `204 No Content`
**エラー**: `404` セッション無し

---

### §7.18 `PATCH /api/novel_db/qa/sessions/{session_id}/title`（B-16）

セッションタイトルを手動更新する。

**リクエストボディ**: `{ "title": "新しいタイトル" }`（1〜100 字）

**レスポンス**: `204 No Content`
**エラー**:
- `404` セッション無し
- `422` `title` 未指定 / 100 字超
