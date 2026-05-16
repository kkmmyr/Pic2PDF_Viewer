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
  - §2.8 `PATCH /api/meta/novel/{book_key}` — novel 1冊メタ部分更新（4.3）
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
  - §7.2b `GET /api/novel_db/authors` — novel 作者一覧（B-21）
  - §7.21 `GET /api/novel_db/books/{book_name}` — 単一書籍の詳細情報
  - §7.3 `POST /api/novel_db/search` — ハイブリッド検索（FTS5 + ベクトル + RRF）
  - §7.4 `POST /api/novel_db/qa` — RAG 質問応答（SSE）
  - §7.5 `GET /api/novel_db/qa/history` — 履歴一覧
  - §7.6 `GET /api/novel_db/qa/history/{id}` — 履歴詳細
  - §7.7 `DELETE /api/novel_db/qa/history/{id}` — 履歴削除
  - §7.8 `POST /api/novel_db/builds` — 再構築ジョブ起動
  - §7.9 `GET /api/novel_db/builds/status` — ジョブキュー状態
  - §7.10 `DELETE /api/novel_db/builds/{job_id}` — 待機中ジョブのキャンセル
  - §7.19 `POST /api/novel/discussion/generate` — 読書会ディスカッション生成（SSE, B-20）
  - §7.20 `GET /api/novel/discussion/history` — ディスカッション履歴一覧（B-20）
- [§9. Amazon CSV インポート（amazon_import）](#9-amazon-csvインポートamazon_import)
  - §9.1 `POST /api/amazon/import` — 固定パス CSV から authors/ASIN を補完
- [§8. 本構築管理（novel_build）](#8-本構築管理novel_build)（4.6）
  - §8.1 `POST /api/novel/build/enqueue` — Full Build ジョブ登録
  - §8.2 `GET /api/novel/build/status` — Full Build キュー状態スナップショット
  - §8.3 `DELETE /api/novel/build/jobs/{job_id}` — 待機中 Full Build ジョブキャンセル
  - §8.4 `GET /api/novel/build/stream` — Full Build キュー状態 SSE ストリーム
- [§10. キャラクタ関係グラフ（novel_graph）](#10-キャラクタ関係グラフnovel_graph)（C-12）
  - §10.1 `GET /api/novel_graph/series` — 関係データ存在シリーズ一覧
  - §10.2 `GET /api/novel_graph/series/{series_id}/books` — シリーズ内書籍一覧
  - §10.3 `GET /api/novel_graph/series/{series_id}/graph` — グラフデータ取得
- [§11. meta.db バックアップ（meta_db_backup）](#11-metadb-バックアップmeta_db_backup)（B-25）
  - §11.1 `POST /api/meta_db/backup` — meta.db バックアップ実行
  - §11.2 `GET /api/meta_db/backup/status` — 最新バックアップ情報

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
ソース別のジャンルリスト（表示順）を返す。ファイルが未作成の場合は meta.db の meta テーブルから既存 `genre` フィールドを収集して初期リストを返す。

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

### §2.8 `PATCH /api/meta/novel/{book_key}`（4.3）

novel ソース 1 冊のメタデータを部分更新する。`{book_key}` は `stem.pdf` 形式（例: `おこぼれ姫と円卓の騎士 1.pdf`）。BookCard の編集ボタン → BookMetaEditModal から呼ばれる。

**パスパラメータ**:
- `book_key` — `{stem}.pdf` 形式。URL エンコード必須。

**リクエストボディ** (すべて任意。省略されたフィールドは変更しない):
```json
{
  "authors": ["石田 リンネ"],
  "series_id": "おこぼれ姫と円卓の騎士",
  "volume": 1,
  "publisher": "ビーズログ文庫",
  "asin": "B009IMAVXC",
  "isbn": "9784047264298",
  "release_date": "2012-09-01"
}
```
- `authors` — 著者名リスト（空配列で削除）
- `series_id` — シリーズ名（`series_title` も同値で設定される）
- `volume` — 巻番号（整数。`null` で削除）
- `publisher` — 出版社・レーベル（空文字で削除）
- `asin` / `isbn` / `release_date` — 空文字で削除

**レスポンス**: `{"message": "Updated"}`

**エラー**: 400 — すべてのフィールドが省略された場合。

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
指定ディレクトリ内の画像から PDF を生成する（doujin ソースは image-only モードのため PDF 生成をスキップし `data/doujin/images/` に WebP を配置する）。comic / novel ソースは PDF を `data/{source}/pdfs/` に保存する。`/pdfs` 静的マウントは廃止済み（[ADR-0003](../02_基本設計/ADR/0003_generated-image-only-mode.md)）。

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
`data/doujin/images/` 配下の全WebP画像を一括で圧縮PDFに変換する。既存ファイルはスキップ。

**リクエストボディ**:
```json
{ "quality": 50 }
```

**レスポンス**: `{"message": "Batch compression complete", "files": [...]}`

---

## §5. OCR

> **2026-05-13 更新**: `ocr_service.py` を `start_batch_ocr.bat`（Phase 5 で削除済み）経由のサブプロセス起動からスレッドベース実装に刷新。`run_ocr_subprocess` + `_store_ocr_pages` を直接呼ぶ。`POST /api/ocr/run` は再び動作する。

### §5.1 `POST /api/ocr/run`

novel OCR を開始する。`services.ocr_service.OCRService` がスレッドを起動し、`run_ocr_subprocess`（yomitoku）でテキスト抽出 → `_store_ocr_pages` で DB 保存。

**クエリパラメータ**:
- `target_dir` (オプション) — 対象書籍ディレクトリ名を指定（省略時は `kindle_novel/images/` 配下の全書籍）

---

### §5.2 `POST /api/ocr/stop`

実行中の OCR を停止要求する（現在処理中の書籍が完了した時点で停止。強制終了ではない）。

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

詳細設計: [機能別/hitomi新着監視設計書.md §6](機能別/hitomi新着監視設計書.md#6-api-仕様)

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
- `force` (オプション、default `false`) — `true` のとき全作者を強制再チェック（通常は当日実行済みの場合スキップ）

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

novel タブのテキスト DB ビューア機能。設計の詳細は [機能別/小説テキスト検索・RAG機能_バックエンド設計.md](機能別/小説テキスト検索・RAG機能_バックエンド設計.md)、要件は 小説テキスト検索・RAG機能.md を参照。

### 共通仕様

- すべてのエンドポイントは `prefix=/api/novel_db`、`tags=["novel_db"]` で登録
- **再構築ジョブ実行中の検索 / 質問**: `503 Service Unavailable` を `Retry-After: 10` ヘッダ付きで返す（[バックエンド設計 §8.2](機能別/小説テキスト検索・RAG機能_バックエンド設計.md)）
- **共通エラーレスポンス**: `{"detail": "<message>"}` 形式（FastAPI 標準）
- **スコープオブジェクト** (`Scope`): 検索 / 質問 / 履歴 で共通の構造
    ```json
    { "type": "all" }                               // 全件
    { "type": "series", "id": "oko-kishi" }         // シリーズ単位
    { "type": "book", "name": "おこぼれ姫と..." }     // 単冊
    ```
    シリーズ未所属書籍は `type=series` の選択肢に含めない（要件定義 TBD-7）。

---

### §7.1 `GET /api/novel_db/books`

novel ソースに登録された書籍一覧と DB 状態を返す。`data/kindle_novel/images/` 配下のサブディレクトリを起点とし、`meta.db` の作者・シリーズ情報と `novel.db` の DB 状態を結合。

**クエリパラメータ**: なし

**レスポンス**:
```json
[
  {
    "name": "おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)",
    "authors": ["田中啓子"],
    "series_id": "54986012bdc6",
    "series_title": "おこぼれ姫と円卓の騎士",
    "series_index": 1.0,
    "is_indexed": true,
    "page_count": 118,
    "indexed_at": "2026-05-09T11:30:00Z",
    "thumbnail_url": "/kindle_novel/images/おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)/001.png",
    "ocr_done_at": "2026-05-09T10:00:00Z",
    "volume": 1,
    "publisher": "ビーズログ文庫",
    "asin": "B00XXXXXX"
  }
]
```

- `is_indexed=false` のとき、`page_count` / `indexed_at` は `null`
- `series_id` / `series_title` はシリーズ未所属の場合 `null`
- `series_index` — DnD 並び替え後の順序（float、`null` は未設定）
- `volume` — 巻番号（整数、表示用。`null` は未設定）
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

### §7.2b `GET /api/novel_db/authors`（B-21）

novel ソースの全書籍から重複なし作者一覧を返す。作者未設定の書籍は除外。`localStorage` に書籍作者を一括設定する際の候補リスト用途。

**レスポンス**:
```json
["石田リンネ", "田中啓子", "山本花子"]
```

文字列配列（アルファベット / 読み昇順）。空配列の可能性あり。

---

### §7.21 `GET /api/novel_db/books/{book_name}`

単一書籍の詳細情報（要約・キャラクター数・ディスカッション数含む）を返す。`NovelDetailPage`（`/novel/detail/:bookName`）から利用。

**パスパラメータ**:
- `book_name` — 書籍名（`{book_name:path}` 形式でスラッシュを含む名称に対応）

**レスポンス例**:
```json
{
  "name": "おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)",
  "authors": ["田中啓子"],
  "series_id": "oko-kishi",
  "series_title": "おこぼれ姫と円卓の騎士",
  "is_indexed": true,
  "page_count": 118,
  "indexed_at": "2026-05-09T11:30:00Z",
  "thumbnail_url": "/kindle_novel/images/.../001.png",
  "ocr_done_at": "2026-05-09T11:25:00Z",
  "volume": 1,
  "publisher": "エンターブレイン",
  "asin": "B00XXXXXX",
  "isbn": null,
  "summary": "レティは……（要約テキスト）",
  "summary_generated_at": "2026-05-10T08:00:00Z",
  "character_count": 12,
  "discussion_count": 3
}
```

- `summary` / `summary_generated_at` は未生成時 `null`
- `character_count` は `characters` テーブルの登録数（0 の可能性あり）
- `discussion_count` は `novel/discussion` で生成済みのディスカッション件数

**エラー**:
- `404`: `book_name` に一致する書籍ディレクトリが存在しない

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

- `snippet` は `<mark>` タグのみ許可（バックエンドで HTML エスケープ済み、フロントは `dangerouslySetInnerHTML` で安全に描画可能、[バックエンド設計 §6.3.1](機能別/小説テキスト検索・RAG機能_バックエンド設計.md)）
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
- クライアントが接続切断（`AbortController.abort()`）した場合、サーバ側で `done_reason='canceled'` として途中までの応答を `qa_history.answer` に保存（[バックエンド設計 §7.6](機能別/小説テキスト検索・RAG機能_バックエンド設計.md)）

**エラー**:
- `422`: `question` が空 / 500 字超 / `scope` 不正
- `503`: 再構築ジョブ実行中（`Retry-After: 10`、SSE 確立前に通常 HTTP レスポンスで返す）

---

### §7.5 `GET /api/novel_db/qa/history`

質問履歴一覧（時系列降順）。各エントリは要約のみ。詳細は §7.6。

**クエリパラメータ**:
- `offset` (default `0`)
- `limit` (default `20`、最大 100)
- `book` (optional): 書籍名文字列。指定時は `scope_type='book' AND scope_id=book` の行のみ返す。未指定時は全件対象（既存の動作と変わらない）

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

履歴詳細（プロンプト全文 / コンテキスト / モデル設定 / 応答メタを含む）。チューニング材料として全項目を保持（要件定義 TBD-2）。

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

### §7.8 `POST /api/novel_db/builds`

再構築ジョブをキューに登録。即座に `job_id` を返し、worker スレッドが順次処理する（[バックエンド設計 §8](機能別/小説テキスト検索・RAG機能_バックエンド設計.md)）。

**リクエストボディ**:
```json
{
  "type": "book",
  "target_id": "おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)",
  "mode": "rebuild"
}
```

| フィールド | 必須 | 値 / デフォルト | 説明 |
|---|---|---|---|
| `type` | ○ | `"book"` / `"series"` / `"all"` | ジョブ単位 |
| `target_id` | △ | — | `type='book'` のとき書籍名、`type='series'` のときシリーズ ID。`type='all'` では省略 |
| `mode` | × | `"rebuild"` (default) / `"ocr"` / `"full_build"` / `"generate_contexts"` / `"generate_relations"` | `rebuild` = pages → chunk/embed 再構築（OCR 済み前提）、`ocr` = 元画像から yomitoku OCR → full_text 更新、`full_build` / `generate_contexts` は §8 の novel_build 管理画面からも指定可、`generate_relations` = キャラ共起カウント + Qwen 関係抽出 → `character_relations` テーブル更新（C-12） |

**レスポンス**:
```json
{
  "job_id": 7,
  "queued_position": 1
}
```

- `queued_position`: キュー内の順番（1 = 次に実行）

**エラー**:
- `422`: 不正な `type` / `target_id` 不一致

---

### §7.9 `GET /api/novel_db/builds/status`

現在のジョブキュー状態を返す。フロントは 5 秒間隔でポーリング（[フロントエンド設計 §6.6](機能別/小説テキスト検索・RAG機能_フロントエンド設計.md)）。

**レスポンス**:
```json
{
  "is_running": true,
  "current_job": {
    "id": 7,
    "type": "all",
    "target_id": null,
    "mode": "rebuild",
    "started_at": "2026-05-09T11:50:00Z",
    "progress_total": 11,
    "progress_done": 4
  },
  "queued_jobs": [
    {
      "id": 8,
      "type": "book",
      "target_id": "おこぼれ姫と円卓の騎士 2 女王の条件 (ビーズログ文庫)",
      "mode": "rebuild",
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

### §7.10 `DELETE /api/novel_db/builds/{job_id}`

待機中ジョブをキャンセル（`state='canceled'` に更新）。

**レスポンス**: `204 No Content`

**エラー**:
- `404`: 該当 `job_id` なし
- `409`: ジョブが実行中（実行中ジョブはキャンセル不可、[バックエンド設計 §8.4](機能別/小説テキスト検索・RAG機能_バックエンド設計.md)）

---

### §7.11 `GET /api/novel_db/books/{book_name}/characters`（B-15）

書籍に登録済みのキャラ一覧を返す。`book_characters` テーブルが空（CLI 未実行）の書籍は `200 []` を返す。生成は `scripts/build_character_summaries.py` で行う（[バックエンド設計 §5.10](機能別/小説テキスト検索・RAG機能_バックエンド設計.md)）。

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

### §7.13 `GET /api/novel_db/sessions`（B-16）

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

### §7.14 `GET /api/novel_db/sessions/{session_id}`（B-16）

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

### §7.15 `POST /api/novel_db/sessions`（B-16、SSE）

会話セッションを新規作成し、初手の質問を SSE で配信する。

**リクエストボディ**:
```json
{
  "scope": { "type": "book", "id": "おこぼれ姫と円卓の騎士 1" },
  "question": "レティの内面はどう変化したか？"
}
```

scope と question から system メッセージ（page 抜粋 + 俯瞰サマリ + 回答ルール）を組み立て、`(system, user)` の 2 メッセージを `qa_messages` に append したうえで LLM ストリーミングを開始する。

**SSE イベント形式（[バックエンド設計 §5.12](機能別/小説テキスト検索・RAG機能_バックエンド設計.md)）**:
- `data: {"token": "..."}` — 部分トークン
- `data: {"done": true, "session_id": 12, "message_id": 22, "eval_count": 432, "done_reason": "stop"}` — 終端
- `data: {"error": "..."}` — 失敗（バックエンド非対応含む）

**エラー**: `503` 再構築ジョブ実行中

---

### §7.16 `POST /api/novel_db/sessions/{session_id}/messages`（B-16、SSE）

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

### §7.17 `DELETE /api/novel_db/sessions/{session_id}`（B-16）

セッションを削除（`qa_messages` も CASCADE で連動削除）。

**レスポンス**: `204 No Content`
**エラー**: `404` セッション無し

---

### §7.18 `PATCH /api/novel_db/sessions/{session_id}/title`（B-16）

セッションタイトルを手動更新する。

**リクエストボディ**: `{ "title": "新しいタイトル" }`（1〜100 字）

**レスポンス**: `204 No Content`
**エラー**:
- `404` セッション無し
- `422` `title` 未指定 / 100 字超

---

### §7.19 `POST /api/novel/discussion/generate`（B-20、SSE）

書籍 1 冊の本文全体を Qwen に読み込ませ、2 人のキャラクター（ペルソナ）が交互に語り合う読書会ディスカッションを SSE ストリーミングで生成する。

**リクエストボディ**:
```json
{
  "book_name": "書籍名",
  "personas": [
    { "name": "批評家", "style_description": "批評家・敬語丁寧・文学評論" },
    { "name": "ファン",  "style_description": "ファン・フランク・感情重視" }
  ],
  "num_turns": 6
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `book_name` | string | 書籍名（novel DB のインデックス済み書籍名） |
| `personas` | array[2] | キャラクター A・B（2 件固定） |
| `personas[].name` | string | 表示名（1〜50 字） |
| `personas[].style_description` | string | 口調・視点の説明（1〜200 字） |
| `num_turns` | integer | 往復数（2〜20、デフォルト 6） |

**レスポンス（SSE ストリーム）**:
```
data: {"type": "turn", "speaker": "A", "text": "この作品の...（完全な発言）"}
data: {"type": "turn", "speaker": "B", "text": "確かに、でも..."}
...
data: {"type": "done", "saved_path": "/path/to/kindle_novel/discussions/書籍名/20260513T143022Z.json"}
data: {"type": "error", "message": "本文が長すぎます（推定 120,000 トークン、上限 112,000 トークン）。"}
```

**事前チェック**: 本文全体のトークン数を推計し、112,000 を超える場合はエラー SSE を即座に返して終了する（生成開始しない）。

**完了時の保存**: `kindle_novel/discussions/{book_name}/{timestamp}Z.json` に全発言を保存。キャンセル（クライアント切断）時は保存しない。

---

### §7.20 `GET /api/novel/discussion/history`（B-20）

指定書籍のディスカッション履歴一覧を返す（新しい順）。turns 全件含む。

**クエリパラメータ**: `book_name` — 書籍名（必須）

**レスポンス**:
```json
[
  {
    "filename": "20260513T143022Z.json",
    "created_at": "2026-05-13T14:30:22+00:00",
    "personas": [
      { "name": "批評家", "style_description": "批評家・敬語丁寧・文学評論" },
      { "name": "ファン",  "style_description": "ファン・フランク・感情重視" }
    ],
    "turn_count": 12,
    "turns": [
      { "speaker": "A", "text": "..." },
      { "speaker": "B", "text": "..." }
    ]
  }
]
```

書籍ディレクトリが存在しない / 履歴ゼロの場合は空配列 `[]` を返す。

---

### §7.21 `GET /api/novel_db/books/{book_name}/similar`（B-19）

指定書籍のサマリ embedding を使い、ライブラリ内の意味的に近い書籍を返す（LanceDB KNN）。自身は除外。サマリが未生成の場合は空配列。

**パスパラメータ**: `book_name` — 書籍名（URL エンコード）

**クエリパラメータ**: `top` — 返す件数（デフォルト: 5、最大: 20）

**レスポンス**:
```json
[
  { "name": "ビーズログ文庫の例 1", "score": 0.7321 },
  { "name": "ビーズログ文庫の例 2", "score": 0.6894 }
]
```

`score` は BGE-M3 正規化 embedding のコサイン類似度近似（0〜1、高いほど類似）。

---

## §9. Amazon CSV インポート（amazon_import）

Amazon 購入履歴 CSV から novel / comic ライブラリの `meta.db` を著者・ASIN で補完するエンドポイント。CSV はサーバー側の固定パス（`AMAZON_DATA_DIR`）から自動読み込みするため、ファイルアップロード不要。

---

### §9.1 `POST /api/amazon/import`

固定パスの Amazon CSV を読み込み、指定ソース（`novel` または `comic`）の `meta.db` を著者・ASIN で補完する。既存値は上書きしない（空欄のみ補完）。

**クエリパラメータ**:

| パラメータ | 必須 | 説明 |
|---|---|---|
| `source` | △ | `novel` または `comic`（デフォルト: `novel`） |

**CSV ソース（サーバー固定パス）**:
- `{AMAZON_DATA_DIR}/amazon-order/Your Amazon Orders/Digital Content Orders.csv` — 全期間エクスポート（ASIN + タイトル）
- `{AMAZON_DATA_DIR}/amazon-order_digital/*.csv` — 月別デジタル注文（著者情報あり、2021 年〜）

**マッチング方式**:
1. 既存エントリに `asin` があれば直接引く
2. ファイル名ステムが正規化タイトル（巻番号/レーベル除去）を含む場合にマッチ

**レスポンス**:
```json
{ "updated": 3, "skipped": 42, "unmatched": 5 }
```

| フィールド | 説明 |
|---|---|
| `updated` | authors/ASIN を補完した件数 |
| `skipped` | 既に両フィールドが埋まっていてスキップした件数 |
| `unmatched` | CSV にマッチする書籍が見つからなかった件数 |

**エラー**:
- `400`: `source` が `novel` / `comic` 以外
- `422`: CSV ファイルが 1 件も見つからない（`AMAZON_DATA_DIR` 確認）

---

## §8. 本構築管理（novel_build）

小説本の Build 処理を管理する専用管理画面 `/novel/build` が使うエンドポイント群（4.6）。内部的には `novel_db` の `job_queue` と同一ワーカーを使い、`mode=full_build`（Step 1+2: Embedding → サマリ + 登場人物）と `mode=generate_contexts`（Step 3: Contextual Retrieval 単独実行、B-23）の 2 モードを扱う。

---

### §8.1 `POST /api/novel/build/enqueue`（4.6）

Build ジョブをキューに登録する。即座に `job_id` を返す。

**リクエストボディ**:
```json
{ "book_name": "花太郎", "all_books": false, "mode": "full_build" }
```

| フィールド | 必須 | 説明 |
|---|---|---|
| `book_name` | △ | 書籍名（`all_books=false` のとき必須） |
| `all_books` | × | `true` のとき全冊一括。省略時 `false` |
| `mode` | × | `"full_build"`（省略時デフォルト）/ `"generate_contexts"`（Step 3 単独、B-23）/ `"generate_relations"`（キャラ関係グラフ生成、C-12） |

**レスポンス**:
```json
{ "job_id": 12, "queued_position": 2 }
```

**エラー**:
- `422`: `all_books=false` なのに `book_name` が空
- `422`: 不正な `mode` 値
- `422`: 同一書籍・同一 mode のジョブが既にキュー / 実行中（`detail: "already queued or running"`）

---

### §8.2 `GET /api/novel/build/status`（4.6）

全キューのスナップショットを返す（`mode=full_build` / `mode=generate_contexts` ジョブを対象）。

**レスポンス**:
```json
{
  "is_running": true,
  "current_job": {
    "id": 12,
    "target_id": "花太郎",
    "mode": "full_build",
    "started_at": "2026-05-13T10:00:00",
    "progress_total": 1,
    "progress_done": 0,
    "current_step": "step 2/2: summarize_book + characters",
    "current_detail": "サマリ生成中"
  },
  "queued_jobs": [
    { "id": 13, "target_id": "千の刀", "mode": "generate_contexts", "enqueued_at": "2026-05-13T10:01:00" }
  ],
  "recent_finished": [
    { "id": 11, "target_id": "鯱", "mode": "full_build", "state": "completed", "finished_at": "2026-05-13T09:55:00", "error_message": null }
  ]
}
```

- `is_running=true` は `full_build` / `generate_contexts` ジョブが実行中のとき
- `recent_finished` は直近 20 件（`completed` / `failed` / `canceled`）
- `current_job.current_step`: 現在実行中のステップ名。`full_build` は `"step 1/2: rebuild_from_pages"` / `"step 2/2: summarize_book + characters"`、`generate_contexts` は `"step 1/1: generate_contexts"`。ステップ開始前は `null`
- `current_job.current_detail`（B-22）: ステップ内の詳細進捗メッセージ（例: `"コンテキスト 50/303 チャンク"`）。未発火時は `null`

---

### §8.3 `DELETE /api/novel/build/jobs/{job_id}`（4.6）

待機中の Full Build ジョブをキャンセル。

**レスポンス**: `204 No Content`

**エラー**:
- `404`: 該当 `job_id` なし
- `409`: ジョブが実行中（実行中ジョブはキャンセル不可）

---

### §8.4 `GET /api/novel/build/stream`（4.6、SSE）

Full Build キューの状態を SSE でストリーミングする。クライアントは `EventSource` で接続し、状態変化のたびにイベントを受信する。

**イベント形式**（1.5 秒ごとにポーリング）:
```
data: {"is_running": true, "current_job": {...}, "queued_jobs": [...], "recent_finished": [...]}

```

- クライアント切断で自動終了
- `Content-Type: text/event-stream`

---

## §10. キャラクタ関係グラフ（novel_graph）

キャラクタ共起カウント + Qwen 関係抽出で生成した `character_relations` テーブルを可視化する API 群（C-12）。生成は `mode=generate_relations` のジョブ（§7.8）で行い、本セクションは読み取り専用エンドポイントのみ。

### §10.1 `GET /api/novel_graph/series`

`character_relations` データが存在するシリーズ一覧を返す。

**レスポンス**:
```json
["おこぼれ姫と円卓の騎士", "七星の剣士"]
```

文字列配列（`series_id` 昇順）。データ未生成の場合は空配列。

---

### §10.2 `GET /api/novel_graph/series/{series_id}/books`

シリーズに含まれる書籍一覧を返す（`character_relations` にデータが存在するもののみ）。

**パスパラメータ**:
- `series_id` — シリーズ ID（URL エンコード必須）

**レスポンス**:
```json
[
  { "id": 3, "name": "おこぼれ姫と円卓の騎士 1 (ビーズログ文庫)" },
  { "id": 4, "name": "おこぼれ姫と円卓の騎士 2 女王の条件 (ビーズログ文庫)" }
]
```

---

### §10.3 `GET /api/novel_graph/series/{series_id}/graph`

シリーズのグラフデータ（nodes / edges）を返す。`NovelGraphPage`（`/novel/graph`）の vis-network 描画に使用。

**パスパラメータ**:
- `series_id` — シリーズ ID（URL エンコード必須）

**クエリパラメータ**:
- `book_ids` (オプション) — カンマ区切りの book_id リスト（省略時は全冊）

**レスポンス**:
```json
{
  "nodes": [
    { "id": 0, "label": "レティ", "book_id": 3 },
    { "id": 1, "label": "デューク", "book_id": 3 }
  ],
  "edges": [
    { "id": 1, "from": 0, "to": 1, "label": "師弟", "weight": 42.0 }
  ]
}
```

- `nodes[].id` — グラフ内一意の整数 ID（冊単位で独立。同名キャラも冊が違えば別ノード）
- `edges[].label` — Qwen が抽出した関係タイプ（未抽出時は空文字）
- `edges[].weight` — 同一ページ共起回数

**エラー**:
- `400`: `book_ids` が整数のカンマ区切りでない
- `404`: 指定 `series_id` の関係データが存在しない

---

## §11. meta.db バックアップ（meta_db_backup）

meta.db を `sqlite3.backup()` で OneDrive 等にスナップショットコピーする API（B-25）。ファイル名形式: `meta_YYYYMMDD_HHMMSS.db`。

### §11.1 `POST /api/meta_db/backup`

meta.db を `META_DB_BACKUP_DIR`（env: `META_DB_BACKUP_DIR`、デフォルト `OneDrive/61.tool/meta_db_backup/`）にコピーする。

**リクエストボディ**: なし

**レスポンス**:
```json
{
  "path": "C:\\Users\\...\\meta_db_backup\\meta_20260517_120000.db",
  "size_bytes": 2097152,
  "backed_up_at": "2026-05-17T12:00:00"
}
```

---

### §11.2 `GET /api/meta_db/backup/status`

最新バックアップの情報を返す。

**レスポンス**:
```json
{
  "last_backup": {
    "path": "C:\\Users\\...\\meta_db_backup\\meta_20260517_120000.db",
    "size_bytes": 2097152,
    "backed_up_at": "2026-05-17T12:00:00"
  },
  "backup_dir": "C:\\Users\\...\\meta_db_backup",
  "total_backups": 5
}
```

- バックアップが 1 件もない場合は `last_backup: null`、`total_backups: 0`
