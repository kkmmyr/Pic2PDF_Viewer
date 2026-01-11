# 詳細設計書

## 1. ディレクトリ構成
```
Pic2PDF_Viewer/
├── backend/
│   ├── data/               # データ格納用
│   │   ├── pdfs/           # PDFファイルの保存・配信場所 (Static Mount)
│   │   ├── thumbnails/     # サムネイル画像の保存・配信場所 (Static Mount)
│   │   ├── images/         # 閲覧用WebP画像の保存・配信場所 (Static Mount)
│   │   └── kindle/         # Kindle専用データ (Static Mount: /kindle/...)
│   │       ├── pdfs/
│   │       ├── thumbnails/
│   │       └── images/
│   ├── services/           # ビジネスロジック (PDF生成など)
│   │   └── pdf_generator.py
│   ├── main.py             # FastAPIエントリーポイント
│   └── requirements.txt    # Python依存関係
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
    *   `source` (オプション) - 'generated' (default) または 'kindle'。ライブラリの参照元を指定。
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
    *   `source` (オプション) - 'generated' (default) または 'kindle'。対象ファイルの場所を指定。
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
    *   `source` (クエリパラメータ, オプション) - 'generated' (default) または 'kindle'。
*   **レスポンス**:
    ```json
    {
      "images": [
        "/images/path/to/book/01.webp",
        "/images/path/to/book/02.webp"
      ]
    }
    ```

## 3. 運用・開発メモ
*   **起動方法**:
    *   Backend: `python -m uvicorn main:app --reload` (Port 8000)
    *   Frontend: `npm run dev` (Port 5173)
*   **注意点**:
    *   `react-pdf` のWorker設定は `unpkg` から動的に読み込む設定になっている。
    *   バックエンドの `data/pdfs` ディレクトリは静的ファイルとして `/pdfs` パスでマウントされている。
    *   バックエンドの `data/thumbnails` ディレクトリは静的ファイルとして `/thumbnails` パスでマウントされている。
