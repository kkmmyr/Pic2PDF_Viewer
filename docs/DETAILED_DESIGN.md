# 詳細設計書

## 1. ディレクトリ構成
```
Pic2PDF_Viewer/
├── backend/
│   ├── data/               # データ格納用
│   │   ├── main/           # メイン（生成済）データ格納用
│   │   │   ├── pdfs/       # PDFファイルの保存・配信場所 (Static Mount)
│   │   │   ├── thumbnails/ # サムネイル画像の保存・配信場所 (Static Mount)
│   │   │   ├── images/     # 閲覧用WebP画像の保存・配信場所 (Static Mount)
│   │   │   └── complete/   # 処理済みソースファイルの移動先
│   │   ├── kindle/         # Kindle専用データ (Static Mount: /kindle/...)
│   │       ├── pdfs/
│   │       ├── thumbnails/
│   │       └── images/
│   │   └── kindle_novel/   # Kindle小説用データ (Static Mount: /kindle_novel/...)
│   │       ├── pdfs/       # Searchable PDF
│   │       ├── thumbnails/
│   │       └── images/     # キャプチャ生画像
│   ├── services/           # ビジネスロジック (PDF生成など)
│   │   └── pdf_generator.py # PDF生成ロジック (PdfGenerator Class)
│   ├── main.py             # FastAPIエントリーポイント
│   └── requirements.txt    # Python依存関係
├── kindle-pdf/             # Kindle自動化ツール
│   ├── main_auto.py        # 漫画/雑誌用エントリーポイント
│   ├── main_novel.py       # 小説用エントリーポイント
│   ├── main_manual.py      # 手動撮影用エントリーポイント
│   ├── capturer.py         # 共通キャプチャロジック (Manga)
│   ├── novel_capturer.py   # 小説用キャプチャロジック (Novel)
│   ├── batch_ocr.py        # OCRバッチ処理スクリプト
│   └── requirements.txt
├── ocr/
│   └── ocr_engine.py       # OCRエンジン抽象化 + Yomitoku実装
├── frontend/
│   ├── src/
│   │   ├── components/     # 共通コンポーネント
│   │   │   ├── Layout.tsx
│   │   │   └── reader/     # リーダー関連コンポーネント
│   │   │       ├── index.ts
│   │   │       ├── PageRenderer.tsx
│   │   │       ├── ReaderHeader.tsx
│   │   │       ├── LibraryHeader.tsx
│   │   │       ├── FolderGrid.tsx
│   │   │       └── PdfGrid.tsx
│   │   ├── config/         # 設定ファイル
│   │   │   └── api.ts      # API URL設定
│   │   ├── hooks/          # カスタムフック
│   │   │   ├── index.ts
│   │   │   ├── useWindowSize.ts
│   │   │   ├── useReaderNavigation.ts
│   │   │   ├── useBookImages.ts
│   │   ├── types/          # 型定義
│   │   │   └── index.ts
│   │   ├── pages/          # ページコンポーネント
│   │   │   ├── ViewerPage.tsx
│   │   │   └── GeneratorPage.tsx
│   │   └── App.tsx         # ルーティング定義
│   └── package.json
└── docs/
    ├── REQUIREMENTS.md     # 要件定義
    ├── BASIC_DESIGN.md     # 基本設計
    └── DETAILED_DESIGN.md  # 本詳細設計書
```

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
      "source_dir": "C:\\Absolute\\Path\\To\\Images"
    }
    ```
*   **レスポンス**: 生成されたファイル名のリスト

### `POST /api/pdfs/{filename}/delete_pages`
*   **パラメータ**: 
    *   `path` (オプション) - 対象ファイルの親ディレクトリパス
    *   `source` (オプション) - 'generated' (default) / 'kindle' / 'novel'。対象ファイルの場所を指定。
*   **リクエストボディ**:
    ```json
    {
      "page_indices": [0, 2, 5]  // 削除するページのインデックス（0始まり）
    }
    ```
*   **レスポンス**:
    ```json
    {
      "message": "Pages deleted successfully",
      "total_pages": 10
    }
    ```

### `GET /api/books/{path}/images`
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
      "source": "generated" // or "kindle"
    }
    ```
*   **レスポンス**: `{"message": "Items moved successfully", "moved_count": 2}`

## 3. クラス設計 (Backend & Kindle Tool)

### `PdfGenerator` (`backend/services/pdf_generator.py`)
*   **役割**: ディレクトリやZIPファイルのスキャン、画像からのPDF生成、ファイル移動を一元管理。
*   **主要メソッド**:
    *   `process_directory()`: 指定ディレクトリ内のWebPをPDF化。
    *   `process_zip()`: ZIPファイル内のWebPをPDF化。
    *   `_create_pdf_file()`: `img2pdf` を用いた実際のPDFファイル書き出し。
    *   `run()`: 処理の実行と、完了ファイルの移動・空ディレクトリ削除の制御。

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
    *   `extract_text()`: 画像からテキストを抽出。
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
