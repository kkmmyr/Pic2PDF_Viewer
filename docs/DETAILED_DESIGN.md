# 詳細設計書

## 1. ディレクトリ構成
```
Pic2PDF_Viewer/
├── backend/
│   ├── data/               # データ格納用
│   │   ├── main/           # メイン（生成済）データ格納用
│   │   │   ├── pdfs/           # PDFファイルの保存・配信場所 (Static Mount: /pdfs)
│   │   │   ├── pdfs_compressed/ # 圧縮版PDFの保存場所 (Static Mount: /pdfs_compressed)
│   │   │   ├── thumbnails/     # サムネイル画像の保存・配信場所 (Static Mount: /thumbnails)
│   │   │   ├── images/         # 閲覧用WebP画像の保存・配信場所 (Static Mount: /images)
│   │   │   └── complete/       # 処理済みソースファイルの移動先
│   │   ├── kindle/         # Kindle専用データ (Static Mount: /kindle/...)
│   │   │   ├── pdfs/
│   │   │   ├── thumbnails/
│   │   │   └── images/
│   │   └── kindle_novel/   # Kindle小説用データ (Static Mount: /kindle_novel/...)
│   │       ├── pdfs/       # Searchable PDF
│   │       ├── thumbnails/
│   │       └── images/     # キャプチャ生画像
│   ├── routers/            # APIルーター
│   │   ├── library.py      # PDFs一覧・書籍画像・フォルダ管理・移動
│   │   ├── pdfs.py         # PDF生成・ページ削除・圧縮
│   │   └── ocr.py          # OCR実行・停止・ステータス
│   ├── services/           # ビジネスロジック
│   │   ├── ocr_service.py  # OCRプロセス管理 (OCRService)
│   │   ├── pdf_generator.py # PDF生成ロジック (PdfGenerator Class)
│   │   ├── pdf_service.py  # PDF操作 (PdfService)
│   │   └── thumbnail_service.py # サムネイル生成 (ThumbnailService)
│   ├── config.py           # パス定数・OCR起動設定
│   ├── main.py             # FastAPIエントリーポイント
│   └── requirements.txt    # Python依存関係
├── kindle-pdf/             # Kindle自動化ツール
│   ├── main_auto.py        # 漫画/雑誌用エントリーポイント
│   ├── main_novel.py       # 小説用エントリーポイント
│   ├── main_manual.py      # 手動撮影用エントリーポイント
│   ├── capturer.py         # 共通キャプチャロジック (Manga)
│   ├── novel_capturer.py   # 小説用キャプチャロジック (Novel)
│   ├── batch_ocr.py        # OCRバッチ処理スクリプト
│   ├── searchable_pdf.py   # SearchablePdfGenerator
│   ├── start_batch_ocr.bat # OCR起動ランチャー (.bat経由)
│   └── requirements.txt
├── ocr/
│   └── ocr_engine.py       # OCRエンジン抽象化 + Yomitoku実装
├── frontend/
│   ├── src/
│   │   ├── components/     # 共通コンポーネント
│   │   │   ├── Layout.tsx  # グローバルレイアウト
│   │   │   └── reader/     # リーダー・ライブラリ関連コンポーネント
│   │   │       ├── index.ts
│   │   │       ├── FolderGrid.tsx
│   │   │       ├── LibraryHeader.tsx
│   │   │       ├── MoveDialog.tsx
│   │   │       ├── PageRenderer.tsx
│   │   │       ├── PdfGrid.tsx
│   │   │       └── ReaderHeader.tsx
│   │   ├── features/       # 機能別モジュール
│   │   │   └── ocr/
│   │   │       └── OCRPanel.tsx  # OCR実行UI
│   │   ├── config/         # 設定ファイル
│   │   │   ├── api.ts      # API URL設定
│   │   │   └── api_client.ts # 共通APIクライアント (axiosベース)
│   │   ├── hooks/          # カスタムフック
│   │   │   ├── index.ts
│   │   │   ├── useWindowSize.ts
│   │   │   ├── useReaderNavigation.ts
│   │   │   ├── useBookImages.ts
│   │   │   ├── useImagePreloader.ts    # 画像先読みフック
│   │   │   ├── useLibraryManagement.ts # ライブラリ操作フック
│   │   │   ├── usePdfStatus.ts         # PDF生成ステータス監視
│   │   │   └── useOcrStatus.ts         # OCRステータス監視
│   │   ├── types/          # 型定義
│   │   │   └── index.ts
│   │   ├── pages/          # ページコンポーネント
│   │   │   ├── ViewerPage.tsx
│   │   │   ├── GeneratorPage.tsx
│   │   │   └── OCRPage.tsx  # OCR実行ページ (/ocr)
│   │   └── App.tsx         # ルーティング定義
│   └── package.json
└── docs/
    ├── REQUIREMENTS.md     # 要件定義
    ├── BASIC_DESIGN.md     # 基本設計
    └── DETAILED_DESIGN.md  # 本詳細設計書
```

### 1.2 データ配置 (Backend)
- `backend/data/`: データ格納ルート
    - `main/`: メイン（生成済）データ格納用
    - `kindle/`: Kindleキャプチャ (漫画)
    - `kindle_novel/`: Kindleキャプチャ (小説)

### 1.3 構成設定 (config.py)
- **パス定数**: `PDF_DIR`, `PDF_COMPRESSED_DIR`, `THUMBNAIL_DIR`, `IMAGES_DIR`, `COMPLETE_DIR`
- **Kindle**: `KINDLE_PDF_DIR`, `KINDLE_THUMBNAIL_DIR`, `KINDLE_IMAGES_DIR`
- **Kindle Novel**: `KINDLE_NOVEL_PDF_DIR`, `KINDLE_NOVEL_THUMBNAIL_DIR`, `KINDLE_NOVEL_IMAGES_DIR`
- **OCR起動設定**: `BATCH_OCR_LAUNCHER` — `kindle-pdf/start_batch_ocr.bat` へのパス。`.bat` ファイル経由で正しいPython環境とPATHを設定してOCRを起動する。


## 2. API仕様

### `GET /api/pdfs`
*   **パラメータ**: 
    *   `path` (オプション) - 表示するサブディレクトリのパス
    *   `source` (オプション) - 'generated' (default) / 'kindle' / 'novel'。ライブラリの参照元を指定。
*   **レスポンス**:
    ```json
    {
      "files": [
        {
          "name": "file1.pdf",
          "thumbnail": "/thumbnails/path/to/file1.jpg"
        },
        {
          "name": "file2.pdf",
          "thumbnail": null
        }
      ],
      "directories": ["subdir1", "subdir2"],
      "current_path": "path/to/current"
    }
    ```

### `POST /api/generate`
*   **リクエストボディ**:
    ```json
    {
      "source_dir": "C:\\Absolute\\Path\\To\\Images",
      "generate_compressed": false,
      "quality": 50
    }
    ```
    - `generate_compressed` (オプション, bool): `true` の場合、圧縮版PDFを `pdfs_compressed/` にも同時生成する。
    - `quality` (オプション, int): 圧縮品質 (1〜95)。`generate_compressed` が `true` の場合のみ使用。
*   **レスポンス**: 生成されたファイル名のリスト

### `GET /api/status`
*   **概要**: PDF生成処理の進捗状況を取得する。
*   **クエリパラメータ**: `source_dir` - スキャン対象のソースディレクトリ
*   **レスポンス**:
    ```json
    {
      "items": [
        {"name": "folder_name", "type": "folder", "status": "not_started"|"in_progress"|"completed"},
        {"name": "zip_name",    "type": "zip",    "status": "not_started"|"in_progress"|"completed"}
      ]
    }
    ```

### `POST /api/batch_compress`
*   **概要**: `data/main/images/` 配下の全WebP画像を一括で圧縮PDFに変換し `pdfs_compressed/` へ出力する。既存ファイルはスキップ。
*   **リクエストボディ**:
    ```json
    { "quality": 50 }
    ```
*   **レスポンス**: `{"message": "Batch compression complete", "files": [...]}`

### `POST /api/pdfs/{filename}/delete_pages`
*   **パラメータ**: 
    *   `path` (オプション) - 対象ファイルの親ディレクトリパス
    *   `source` (オプション) - 'generated' (default) / 'kindle' / 'novel'。対象ファイルの場所を指定。
*   **リクエストボディ**:
    ```json
    {
      "page_indices": [0, 2, 5]
    }
    ```
*   **レスポンス**:
    ```json
    {
      "message": "Pages deleted successfully",
      "total_pages": 10
    }
    ```

### 3. OCR API
- **POST /api/ocr/run**: Novel用OCR処理 (`batch_ocr.py`) の実行を開始する。
- **POST /api/ocr/stop**: 実行中のOCRプロセスを停止する。
- **GET /api/ocr/status**: 現在のOCRプロセスのステータスとログを取得する。
    - Response: `{ status: "idle"|"running"|"error", logs: string[], last_return_code: number|null }`

### `GET /api/books/{path}/images`
*   **概要**: 指定された書籍（フォルダまたはZIP）の画像リストとサイズ情報を取得。
*   **パラメータ**: 
    *   `path` (パスパラメータ) - 書籍（フォルダまたはZIP）の相対パス
    *   `source` (クエリパラメータ, オプション) - 'generated' (default) / 'kindle' / 'novel'。
*   **レスポンス**:
    ```json
    {
      "images": [
        "/images/path/to/book/01.webp",
        "/images/path/to/book/02.webp"
      ]
    }
    ```

### `POST /api/directories`
*   **概要**: フォルダ作成
*   **リクエストボディ**:
    ```json
    {
      "path": "current/relative/path",
      "name": "new_folder_name",
      "source": "generated" // or "kindle"
    }
    ```
*   **レスポンス**: `{"message": "Directory created"}`

### `POST /api/move`
*   **概要**: ファイル・フォルダ移動
*   **リクエストボディ**:
    ```json
    {
      "items": ["file1.pdf", "subfolder"],
      "source_path": "current/relative/path",
      "destination_path": "dest/relative/path",
      "source": "generated"
    }
    ```
*   **レスポンス**: `{"message": "Items moved", "moved_count": 2, "errors": []}`
    - `errors`: 個別アイテムのエラーメッセージリスト（成功時は空配列）

## 3. クラス設計 (Backend & Kindle Tool)

### `OCRService` (`backend/services/ocr_service.py`)
*   **役割**: OCRバックグラウンドプロセスの管理、ログ収集、ステータス管理。
*   **主要メソッド**:
    *   `start_ocr()`: `batch_ocr.py` をサブプロセスとして起動。UTF-8エンコーディングを強制。
    *   `stop_ocr()`: 実行中のプロセスを停止 (Terminate/Kill)。
    *   `get_status()`: 現在の状態と直近のログを返却。

### `PdfGenerator` (`backend/services/pdf_generator.py`)
*   **役割**: ディレクトリやZIPファイルのスキャン、画像からのPDF生成、ファイル移動を一元管理。
*   **主要メソッド**:
    *   `process_directory()`: 指定ディレクトリ内のWebPをPDF化。
    *   `process_zip()`: ZIPファイル内のWebPをPDF化。
    *   `_create_pdf_file()`: `img2pdf` を用いた実際のPDFファイル書き出し。
    *   `run()`: 処理の実行と、完了ファイルの移動・空ディレクトリ削除の制御。

### `PdfService` (`backend/services/pdf_service.py`)
*   **役割**: 既存PDFの編集操作を一元管理。
*   **主要メソッド**:
    *   `delete_pages()`: 指定されたページの削除とPDFの再保存。
    *   `get_page_count()`: PDFの総ページ数を取得。

### `ThumbnailService` (`backend/services/thumbnail_service.py`)
*   **役割**: PDFからのサムネイル画像生成。
*   **主要メソッド**:
    *   `generate_thumbnail()`: 最初のページを座標指定またはスケール指定で画像出力。

### `KindleCapturer` (`kindle-pdf/capturer.py`)
*   **役割**: 基本的なKindleウィンドウ操作、スクリーンショット撮影、PDF作成。
*   **主要メソッド**:
    *   `find_window()`: Kindleウィンドウのハンドル取得。
    *   `get_book_title()`: タイトル入力ダイアログ（`BookInfoDialog`）の表示。
    *   `capture_loop()`: ページめくりと撮影のループ。

### `AutoKindleCapturer` (`capturer.py`)
*   **継承**: `KindleCapturer`
*   **役割**: 漫画/雑誌用の自動クロップ（黒帯検出）。
*   **特徴**: フルスクリーンモードを使用。

### `NovelKindleCapturer` (`novel_capturer.py`)
*   **継承**: `AutoKindleCapturer`
*   **役割**: 小説用の自動クロップ（X軸白背景検出）と画像保存。
*   **変更点**: OCR/PDF生成機能は削除（`batch_ocr.py`へ委譲）。撮影速度を優先。

### `SearchablePdfGenerator` (`kindle-pdf/searchable_pdf.py`)
*   **役割**: 画像とOCR結果から「透明テキスト付きPDF」を生成する。
*   **使用ライブラリ**: `ReportLab`
*   **特徴**:
    *   `add_page(image_path, ocr_results)`: 画像を描画し、その上に検索用テキスト（透明）を配置する。
    *   `_draw_text_layer`: 縦書き判定と文字回転、`TextObject` を用いた描画モード制御。

### `BatchOCR` (`kindle-pdf/batch_ocr.py`)
*   **役割**: `kindle_novel/images` 配下の新規フォルダを監視し、自動的にSearchable PDF化する。
*   **フロー**: フォルダ検知 -> OCR (`yomitoku`) -> PDF生成 (`SearchablePdfGenerator`)。

### `BookInfoDialog` (`capturer.py`)
*   **役割**: 書籍情報入力ダイアログ。
*   **入力**: タイトル、ページめくり方向（左キー/右キー）。

### `YomitokuEngine` (`ocr/ocr_engine.py`)
*   **役割**: `yomitoku` ライブラリを用いたOCR処理。
*   **特徴**:
    *   `extract_text()`: 画像からテキストを抽出。段落判定または単語判定に分岐。
    *   `_process_paragraphs()`: 段落情報の処理。フリガナ除去フィルタ(`_calculate_thickness`)を含む。
    *   `_process_words()`: 単語情報の処理。座標ソートとフリガナ除去フィルタを含む。
    *   **Fallback Logic**: 段落検出失敗時に、座標ベースで読み順をソートするロジックを実装。
    *   **Furigana Filter**: 文字サイズ（厚み）によるフリガナ除去フィルタ。

## 4. 運用・開発メモ

*   **起動方法**:
    *   Backend: `python -m uvicorn main:app --reload` (Port 8000)
    *   Frontend: `npm run dev` (Port 5173)
*   **注意点**:
    *   `react-pdf` のWorker設定は `unpkg` から動的に読み込む設定になっている。
    *   バックエンドの `data/pdfs` ディレクトリは静的ファイルとして `/pdfs` パスでマウントされている。
    *   バックエンドの `data/thumbnails` ディレクトリは静的ファイルとして `/thumbnails` パスでマウントされている。
*   **環境設定**:
    *   Frontend: `frontend/.env` に `VITE_DEFAULT_SOURCE_DIR` を設定することで、生成画面のデフォルトパスを変更可能。
    *   Backend: サービス層の抽出により、ロジックの単体テストが容易な構成になっている。
