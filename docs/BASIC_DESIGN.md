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
*   **Kindle Tool** (Python Client)
    *   GUI自動化: `pyautogui`
    *   画像処理: `opencv-python` (cv2), `Pillow`
    *   OCR (Novel): `yomitoku` (Deep Learning based OCR), `torch`

### 1.2. データフロー

#### 1. PDF生成
1.  **Client** -> `POST /api/generate` (source_dir) -> **Server**
2.  **Server** -> `scan_and_generate` -> **File System** (Read WebP, Write PDF & Thumbnail)
3.  **Server** -> Response (Generated File List) -> **Client**

#### 2. PDF一覧・閲覧
1.  **Client** -> `GET /api/pdfs?path=...&source=[generated|kindle|novel]` -> **Server**
2.  **Server** -> `source` パラメータに基づき、対象ディレクトリ (`data/pdfs`, `data/kindle/pdfs`, `data/kindle_novel/pdfs`) をスキャン。
3.  **Server** -> Response (Files with Thumbnail URLs) -> **Client**
4.  **Client** -> `GET` Static Files -> **Server** -> PDF Stream / Thumbnails -> **Client**

#### 3. Kindleキャプチャ (External Tool)
*   **Manga/Manual**: `kindle-pdf/main_auto.py` / `main_manual.py`
    1.  Capture Screen -> Crop.
    2.  Save Images -> Create PDF (`data/kindle/pdfs`).
*   **Novel**: `kindle-pdf/main_novel.py`
    1.  Capture Screen -> **Dynamic Crop** (X-Axis only, White BG detection).
    2.  Save Images ONLY to `data/kindle_novel/images`. (No OCR at capture time).

#### 4. Novel Batch OCR (Background Processing)
*   **Script**: `kindle-pdf/batch_ocr.py`
    1.  **Auto Scan**: Checks `data/kindle_novel/images` for all book folders.
    2.  **Skip Check**: Skips if corresponding PDF already exists in `data/kindle_novel/pdfs`.
    3.  **Process**:
        *   Load Images.
        *   **OCR Engine** (`yomitoku`) -> Extract Text & Layout.
        *   **PDF Gen** (`SearchablePdfGenerator`) -> Create PDF with invisible text overlay.
    4.  **Output**: Save Searchable PDF to `data/kindle_novel/pdfs`.
