# Pic2PDF Viewer プロジェクト仕様書

このドキュメントは、Pic2PDF Viewerアプリケーションの要件、設計、および実装の詳細をまとめたものです。
機能の追加や変更を行う際は、本ドキュメントも併せて更新してください。

## 1. 要件定義

### 1.1. 目的
WebP画像を管理・閲覧するためのWebアプリケーション。
大量の画像をPDFとしてまとめ、ブラウザ上で快適に閲覧することを目的とする。

### 1.2. 主な機能
1.  **PDF生成 (Generator)**
    *   指定した親ディレクトリ以下を再帰的に走査する。
    *   **フォルダ処理**: 各ディレクトリ内のWebP画像を収集し、ファイル名の「自然順」でソートしてPDF化。出力名は `<フォルダ名>.pdf`。
    *   **ZIPファイル処理**: ディレクトリ内の `.zip` ファイルを検知し、中のWebP画像を同様にソートしてPDF化。出力名は `<ZIPファイル名>.pdf`。
    *   1つのPDFファイルに結合し、`backend/pdfs` ディレクトリ（またはそのサブディレクトリ）に出力する。
    *   **完了後の処理**: PDF生成が成功したフォルダまたはZIPファイルは、`backend/complete` ディレクトリに移動される。

2.  **PDF閲覧 (Viewer)**
    *   `backend/pdfs` 配下のPDFファイルおよびディレクトリを一覧表示する。
    *   **フォルダ階層表示**:
        *   サブディレクトリがある場合はフォルダアイコンで表示。
        *   クリックすることで階層を降り（ドリルダウン）、戻るボタンで親階層に戻ることができる。
    *   **サムネイル表示**:
        *   PDFファイルは1ページ目をサムネイルとして表示する。
    *   **リーダー機能**:
        *   **見開き表示**: デフォルトで2ページ表示（見開き）とする。
        *   **右綴じ（RTL）**: 一般的な漫画と同様、右側が若いページ（例: 1ページ）、左側が次のページ（例: 2ページ）となる配置。
        *   **没入型モード (Immersive Mode)**:
            *   PDF閲覧中はグローバルヘッダーを非表示にし、コンテンツ領域を最大化する。
            *   リーダー上部のコントロールバーはマウスオーバー時のみ表示され、閲覧の邪魔にならないようにする。
        *   **ページ送り操作**:
            *   左側（次ページ側）クリック: 次の見開きへ進む。
            *   右側（現ページ側）クリック: 前の見開きへ戻る。
            *   **キーボード操作**:
                *   矢印キー（←/→）でページ送りが可能。
                *   RTL/LTRの設定に応じて、直感的な方向（例: RTLなら左キーで「次へ」）に移動する。
    *   **ナビゲーション**:
        *   URLパラメータ (`?path=...`, `?file=...`) を使用して状態を管理。
        *   ブラウザの「戻る」「進む」ボタンで、フォルダ移動やPDFの開閉履歴を辿ることができる。
    *   **編集機能**:
        *   **ページ削除**:
            *   PDF閲覧画面で「編集モード」に切り替えることで、任意のページを選択して削除できる。
            *   削除実行後、ファイルは上書き保存され、サムネイルも必要に応じて更新される。
    *   **高速閲覧モード (Image-Based Viewing)**:
        *   PDF生成時に抽出されたWebP画像が存在する場合、PDFレンダリングの代わりに画像を直接読み込んで表示する。
        *   これにより、特に高解像度の書籍において、PDFのパース処理をスキップして高速にページを表示できる。
        *   画像が存在しない場合は、従来のPDFレンダリング（`react-pdf`）に自動的にフォールバックする。

## 2. アーキテクチャ設計

### 2.1. 技術スタック
*   **Frontend**: React (Vite), TypeScript, TailwindCSS
    *   PDF描画: `react-pdf`
    *   ルーティング: `react-router-dom`
    *   アイコン: `lucide-react`
*   **Backend**: Python (FastAPI)
    *   PDF変換: `img2pdf`, `Pillow`
    *   サムネイル生成: `Pillow` (生成時), `pymupdf` (既存PDF読み込み時)
    *   ソート: `natsort`
    *   サーバー: `uvicorn`

### 2.2. ディレクトリ構成
```
Pic2PDF_Viewer/
├── backend/
│   ├── data/               # データ格納用
│   │   ├── pdfs/           # PDFファイルの保存・配信場所 (Static Mount)
│   │   ├── thumbnails/     # サムネイル画像の保存・配信場所 (Static Mount)
│   │   └── images/         # 閲覧用WebP画像の保存・配信場所 (Static Mount)
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
│   │   │   └── useBookImages.ts
│   │   ├── types/          # 型定義
│   │   │   └── index.ts
│   │   ├── pages/          # ページコンポーネント
│   │   │   ├── ViewerPage.tsx
│   │   │   └── GeneratorPage.tsx
│   │   └── App.tsx         # ルーティング定義
│   └── package.json
└── docs/
    └── project_spec.md     # 本仕様書
```

### 2.3. データフロー
1.  **PDF生成**:
    *   Client -> `POST /api/generate` (source_dir) -> Server
    *   Server -> `scan_and_generate` -> File System (Read WebP, Write PDF & Thumbnail)
    *   Server -> Response (Generated File List) -> Client

2.  **PDF一覧・閲覧**:
    *   Client -> `GET /api/pdfs?path=...` -> Server
    *   Server -> `os.listdir` (Target Dir) -> Check Thumbnails
        *   **サムネイル自動生成**: サムネイルがないPDFがあれば、バックグラウンドタスクで生成 (`pymupdf` 使用) を予約。
    *   Server -> Response (Files with Thumbnail URLs) -> Client
    *   Client -> `GET /pdfs/...` (Static File) -> Server -> PDF Stream -> Client (Render via react-pdf)
    *   Client -> `GET /thumbnails/...` (Static File) -> Server -> Image -> Client (Render via img tag)

## 3. API仕様

### `GET /api/pdfs`
*   **パラメータ**: `path` (オプション) - 表示するサブディレクトリのパス
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
*   **パラメータ**: `path` (オプション) - 対象ファイルの親ディレクトリパス
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
*   **パラメータ**: `path` (パスパラメータ) - 書籍（フォルダまたはZIP）の相対パス（拡張子なし、またはフォルダ名）
*   **レスポンス**:
    ```json
    {
      "images": [
        "/images/path/to/book/01.webp",
        "/images/path/to/book/02.webp"
      ]
    }
    ```

## 4. 運用・開発メモ
*   **起動方法**:
    *   Backend: `python -m uvicorn main:app --reload` (Port 8000)
    *   Frontend: `npm run dev` (Port 5173)
*   **注意点**:
    *   `react-pdf` のWorker設定は `unpkg` から動的に読み込む設定になっている。
    *   バックエンドの `data/pdfs` ディレクトリは静的ファイルとして `/pdfs` パスでマウントされている。
    *   バックエンドの `data/thumbnails` ディレクトリは静的ファイルとして `/thumbnails` パスでマウントされている。
