# 基本設計書

## 1. アーキテクチャ設計

### 1.1. 技術スタック
*   **Frontend**: React (Vite), TypeScript, TailwindCSS
    *   PDF描画: `react-pdf`
    *   ルーティング: `react-router-dom`
    *   アイコン: `lucide-react`
*   **Backend**: Python (FastAPI)
    *   PDF変換: `img2pdf`, `Pillow`
    *   サムネイル生成: `Pillow` (生成時), `pymupdf` (既存PDF読み込み時)
    *   ソート: `natsort`
    *   サーバー: `uvicorn`

### 1.2. データフロー

#### 1. PDF生成
1.  **Client** -> `POST /api/generate` (source_dir) -> **Server**
2.  **Server** -> `scan_and_generate` -> **File System** (Read WebP, Write PDF & Thumbnail)
3.  **Server** -> Response (Generated File List) -> **Client**

#### 2. PDF一覧・閲覧
1.  **Client** -> `GET /api/pdfs?path=...&source=[generated|kindle]` -> **Server**
2.  **Server** -> `source` パラメータに基づき、対象ディレクトリ (`data/pdfs` or `data/kindle/pdfs`) をスキャン。
3.  **Server** -> Response (Files with Thumbnail URLs) -> **Client**
4.  **Client** -> `GET /[kindle/]pdfs/...` (Static File) -> **Server** -> PDF Stream -> **Client**
5.  **Client** -> `GET /[kindle/]thumbnails/...` (Static File) -> **Server** -> Image -> **Client**

#### 3. Kindleキャプチャ (External Tool)
1.  **Tool** (`kindle-pdf`) -> Capture & Generate -> **File System** (`data/kindle/images`, `data/kindle/pdfs`)
2.  **Viewer** -> Kindle Tab -> Displays generated content.
