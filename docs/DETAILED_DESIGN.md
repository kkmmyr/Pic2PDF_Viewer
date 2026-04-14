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
│   ├── utils/
│   │   ├── path_utils.py   # パスバリデーション一元化
│   │   └── logger.py       # ロギング設定
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
├── start.bat               # バックエンド・フロントエンド同時起動スクリプト
├── 起動方法.md              # 起動手順メモ
├── frontend/
│   ├── src/
│   │   ├── components/     # 共通コンポーネント
│   │   │   ├── Layout.tsx  # グローバルレイアウト
│   │   │   ├── ErrorBoundary.tsx # エラーバウンダリ
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
│   │   │   ├── usePolling.ts           # 共通ポーリングフック
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
    ├── BASIC_DESIGN.md     # 基本設計（技術スタック・データフロー）
    ├── DETAILED_DESIGN.md  # 本詳細設計書（ディレクトリ構成・クラス設計）
    ├── API_SPEC.md         # API仕様
    ├── OCR_DESIGN.md       # OCR設計・改善記録
    ├── GPU_SETUP.md        # GPU環境セットアップ手順
    └── CHANGELOG.md        # 変更履歴
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

---

## 2. クラス設計

### バックエンド (`backend/`)

#### `OCRService` (`backend/services/ocr_service.py`)
- **役割**: OCRバックグラウンドプロセスの管理、ログ収集、ステータス管理。
- **主要メソッド**:
    - `start_ocr()`: `batch_ocr.py` をサブプロセスとして起動。UTF-8エンコーディングを強制。
    - `stop_ocr()`: 実行中のプロセスを停止 (Terminate/Kill)。
    - `get_status()`: 現在の状態と直近のログを返却。

#### `PdfGenerator` (`backend/services/pdf_generator.py`)
- **役割**: ディレクトリやZIPファイルのスキャン、画像からのPDF生成、ファイル移動を一元管理。
- **主要メソッド**:
    - `process_directory()`: 指定ディレクトリ内のWebPをPDF化。
    - `process_zip()`: ZIPファイル内のWebPをPDF化。
    - `_process_images()`: サムネイル生成・PDF生成・画像移動の共通処理。
    - `run()`: 処理の実行と、完了ファイルの移動・空ディレクトリ削除の制御。

#### `PdfService` (`backend/services/pdf_service.py`)
- **役割**: 既存PDFの編集操作を一元管理。
- **主要メソッド**:
    - `delete_pages()`: 指定されたページの削除とPDFの再保存。
    - `get_page_count()`: PDFの総ページ数を取得。

#### `ThumbnailService` (`backend/services/thumbnail_service.py`)
- **役割**: PDFからのサムネイル画像生成。
- **主要メソッド**:
    - `generate_thumbnail()`: 最初のページを座標指定またはスケール指定で画像出力。

---

### Kindleキャプチャツール (`kindle-pdf/`)

#### `KindleCapturer` (`kindle-pdf/capturer.py`)
- **役割**: 基本的なKindleウィンドウ操作、スクリーンショット撮影、PDF作成。
- **主要メソッド**:
    - `find_window()`: Kindleウィンドウのハンドル取得。
    - `get_book_title()`: タイトル入力ダイアログ（`BookInfoDialog`）の表示。
    - `capture_loop()`: ページめくりと撮影のループ。

#### `AutoKindleCapturer` (`capturer.py`)
- **継承**: `KindleCapturer`
- **役割**: 漫画/雑誌用の自動クロップ（黒帯検出）。フルスクリーンモードを使用。

#### `NovelKindleCapturer` (`novel_capturer.py`)
- **継承**: `AutoKindleCapturer`
- **役割**: 小説用の自動クロップ（X軸白背景検出）と画像保存。
- **特徴**: OCR/PDF生成機能は削除（`batch_ocr.py`へ委譲）。撮影速度を優先。

#### `BookInfoDialog` (`capturer.py`)
- **役割**: 書籍情報入力ダイアログ。
- **入力**: タイトル、ページめくり方向（左キー/右キー）。

#### `SearchablePdfGenerator` (`kindle-pdf/searchable_pdf.py`)
- **役割**: 画像とOCR結果から「透明テキスト付きPDF」を生成する。
- **使用ライブラリ**: `ReportLab`
- **主要メソッド**:
    - `add_page(image_path, ocr_results)`: 画像を描画し、その上に検索用テキスト（透明）を配置する。
    - `_draw_vertical_text`: **1文字ずつ個別の `TextObject` で縦に配置**（旧: `-90°` 回転+`textOut(全文)` 方式は廃止）。
    - `_draw_horizontal_text`: 横書き（ルビ等）の配置。
- 詳細設計: [OCR_DESIGN.md](OCR_DESIGN.md)

#### `BatchOCR` (`kindle-pdf/batch_ocr.py`)
- **役割**: `kindle_novel/images` 配下の未処理フォルダを走査し、自動的にSearchable PDF化する。
- **フロー**: フォルダ検知 → OCR (`yomitoku`) → PDF生成 (`SearchablePdfGenerator`)

---

### OCRエンジン (`D:\61.tool\common\ocr\`)

#### `YomitokuEngine` (`ocr_engine.py`)
- **役割**: `yomitoku` ライブラリを用いたOCR処理。
- **主要メソッド**:
    - `extract_text()`: 画像からテキストを抽出。段落判定または単語判定に分岐。
    - `_process_words()`: 単語情報の処理。thickness統一・aspect比判定・フリガナ除去・正規化。
    - `filter_ruby_text()`: ヒストグラム谷（valley）自動検出によるフリガナ除去。
    - `normalize_text()`: 3点リーダー・特殊記号の正規化。
- 詳細設計: [OCR_DESIGN.md](OCR_DESIGN.md)

---

## 3. 運用・開発メモ

- **起動方法**: [起動方法.md](../起動方法.md) を参照
    - Backend: `python -m uvicorn main:app --reload` (Port 8000)
    - Frontend: `npm run dev` (Port 5173)
- **注意点**:
    - `react-pdf` のWorker設定は `unpkg` から動的に読み込む設定になっている。
    - `data/pdfs` / `data/thumbnails` は静的ファイルとして `/pdfs` / `/thumbnails` パスでマウントされている。
- **環境設定**:
    - Frontend: `frontend/.env` に `VITE_DEFAULT_SOURCE_DIR` を設定することで生成画面のデフォルトパスを変更可能。
    - Backend: `python-dotenv` 導入済み。`.env` ファイルから設定を読み込む。
