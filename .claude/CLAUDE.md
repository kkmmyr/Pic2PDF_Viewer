# グローバル設定

## 使用中のMCPサーバー

- **gemma-local** — ローカルのGemma 4:e4b モデル。コード説明・翻訳・生成・画像解析タスクをClaudeの代わりに処理してコストを節約する。ツール: ask_gemma / explain_code / generate_code / translate_text / analyze_image

利用基準の詳細は `D:\61.tool\Gemma 4\docs\gemma_tool_usage_guide.md` を参照すること。


---

## プロジェクト概要

WebP画像・ZIPをPDF化してブラウザで閲覧するWebアプリ。Kindleキャプチャ連携とOCR（yomitoku）によるSearchable PDF生成機能あり。

- 要件: [docs/01_要件定義/要件定義書.md](../docs/01_要件定義/要件定義書.md)
- 基本設計: [docs/02_基本設計/基本設計書.md](../docs/02_基本設計/基本設計書.md)
- 詳細設計: [docs/03_詳細設計/詳細設計書.md](../docs/03_詳細設計/詳細設計書.md)
- API: [docs/03_詳細設計/API仕様書.md](../docs/03_詳細設計/API仕様書.md)
- OCR: [docs/03_詳細設計/OCR設計書.md](../docs/03_詳細設計/OCR設計書.md)
- 変更履歴: [docs/05_記録/変更履歴.md](../docs/05_記録/変更履歴.md)

---

## 起動方法

```bash
# バックエンド
cd backend && python -m uvicorn main:app --reload  # :8000

# フロントエンド
cd frontend && npm run dev  # :5173
```

詳細: [起動方法.md](../起動方法.md)

---

## アーキテクチャ

### バックエンド (FastAPI / Python)

| ファイル | 役割 |
|---|---|
| [backend/main.py](../backend/main.py) | アプリ起動・ルーター登録・静的ファイルマウント |
| [backend/config.py](../backend/config.py) | データディレクトリ定数・`get_dirs_by_source()` |
| [backend/routers/library.py](../backend/routers/library.py) | ライブラリ一覧・フォルダ管理・リネームAPI |
| [backend/routers/pdfs.py](../backend/routers/pdfs.py) | PDF生成（非同期ジョブ）・ページ削除・圧縮API |
| [backend/routers/ocr.py](../backend/routers/ocr.py) | OCR実行・停止・ステータスAPI |
| [backend/routers/meta.py](../backend/routers/meta.py) | 書籍メタデータ（作者名）取得・更新API |
| [backend/services/pdf_service.py](../backend/services/pdf_service.py) | PDFページ削除・ページ数取得ロジック |
| [backend/services/pdf_generator.py](../backend/services/pdf_generator.py) | WebP/ZIP → PDF変換 |
| [backend/services/thumbnail_service.py](../backend/services/thumbnail_service.py) | サムネイル生成 |
| [backend/services/ocr_service.py](../backend/services/ocr_service.py) | OCRバックグラウンドプロセス管理 |

**主要ライブラリ:** `fastapi`, `uvicorn`, `img2pdf`, `Pillow`, `pymupdf`, `natsort`

### フロントエンド (React + TypeScript + Vite)

**ページ**

| ファイル | 役割 |
|---|---|
| [frontend/src/App.tsx](../frontend/src/App.tsx) | ルーティング (`/viewer`, `/generator`, `/ocr`) |
| [frontend/src/pages/ViewerPage.tsx](../frontend/src/pages/ViewerPage.tsx) | PDFライブラリ・リーダー統合ページ |
| [frontend/src/pages/GeneratorPage.tsx](../frontend/src/pages/GeneratorPage.tsx) | PDF生成ページ |
| [frontend/src/pages/OCRPage.tsx](../frontend/src/pages/OCRPage.tsx) | Novel OCR実行ページ |

**コンポーネント (viewer/ — 状態管理層)**

| ファイル | 役割 |
|---|---|
| [frontend/src/components/viewer/LibraryPanel.tsx](../frontend/src/components/viewer/LibraryPanel.tsx) | ライブラリUI（一覧・ソート・お気に入り・作者フィルター） |
| [frontend/src/components/viewer/ReaderPanel.tsx](../frontend/src/components/viewer/ReaderPanel.tsx) | PDFリーダーUI（ページ表示・見開き制御・検索・削除） |
| [frontend/src/components/viewer/BulkAuthorDialog.tsx](../frontend/src/components/viewer/BulkAuthorDialog.tsx) | 複数書籍への作者名一括設定ダイアログ |
| [frontend/src/components/viewer/CreateFolderDialog.tsx](../frontend/src/components/viewer/CreateFolderDialog.tsx) | フォルダ作成ダイアログ |
| [frontend/src/components/viewer/RenameDialog.tsx](../frontend/src/components/viewer/RenameDialog.tsx) | PDF/フォルダ共用リネームダイアログ |

**コンポーネント (reader/ — プレゼンテーション層)**

| ファイル | 役割 |
|---|---|
| [frontend/src/components/reader/ReaderHeader.tsx](../frontend/src/components/reader/ReaderHeader.tsx) | リーダーヘッダー（見開きモード・方向・検索・編集ボタン） |
| [frontend/src/components/reader/PageRenderer.tsx](../frontend/src/components/reader/PageRenderer.tsx) | 単一ページ描画（PDF/画像モード・ページサイズ通知） |
| [frontend/src/components/reader/LibraryHeader.tsx](../frontend/src/components/reader/LibraryHeader.tsx) | ライブラリヘッダー（検索・ソート・作者フィルター・選択モード） |
| [frontend/src/components/reader/PdfGrid.tsx](../frontend/src/components/reader/PdfGrid.tsx) | 書籍カードグリッド（サムネイル・作者名表示） |
| [frontend/src/components/reader/FolderGrid.tsx](../frontend/src/components/reader/FolderGrid.tsx) | フォルダカードグリッド |
| [frontend/src/components/reader/PdfSearchBar.tsx](../frontend/src/components/reader/PdfSearchBar.tsx) | PDF内テキスト検索バー |
| [frontend/src/components/reader/LazyThumbnail.tsx](../frontend/src/components/reader/LazyThumbnail.tsx) | サムネイル遅延読み込み (IntersectionObserver) |
| [frontend/src/components/reader/MoveDialog.tsx](../frontend/src/components/reader/MoveDialog.tsx) | 書籍移動ダイアログ |

**カスタムフック (hooks/)**

| ファイル | 役割 |
|---|---|
| [frontend/src/hooks/useBookMeta.ts](../frontend/src/hooks/useBookMeta.ts) | 書籍メタデータ（作者名）取得・更新・全作者集計 |
| [frontend/src/hooks/useLibraryManagement.ts](../frontend/src/hooks/useLibraryManagement.ts) | ライブラリ操作（フォルダ作成・移動・リネーム） |
| [frontend/src/hooks/useReaderNavigation.ts](../frontend/src/hooks/useReaderNavigation.ts) | ページナビゲーション（前/次・ジャンプ・リセット） |
| [frontend/src/hooks/useBookImages.ts](../frontend/src/hooks/useBookImages.ts) | 書籍画像URL取得・画像モード判定 |
| [frontend/src/hooks/useImagePreloader.ts](../frontend/src/hooks/useImagePreloader.ts) | 画像先読み |
| [frontend/src/hooks/useSortedPdfs.ts](../frontend/src/hooks/useSortedPdfs.ts) | PDF一覧並び替え (useMemo) |
| [frontend/src/hooks/useFavorites.ts](../frontend/src/hooks/useFavorites.ts) | お気に入り管理 (source別localStorage) |
| [frontend/src/hooks/useDarkMode.ts](../frontend/src/hooks/useDarkMode.ts) | ダークモード管理 (localStorage永続化) |
| [frontend/src/hooks/useUrlState.ts](../frontend/src/hooks/useUrlState.ts) | URLパラメータ同期 (path/file/source の読み書き) |
| [frontend/src/hooks/usePolling.ts](../frontend/src/hooks/usePolling.ts) | 共通ポーリングフック |
| [frontend/src/hooks/usePdfStatus.ts](../frontend/src/hooks/usePdfStatus.ts) | PDF生成ジョブ監視 |
| [frontend/src/hooks/useOcrStatus.ts](../frontend/src/hooks/useOcrStatus.ts) | OCRステータス監視 |
| [frontend/src/hooks/useWindowSize.ts](../frontend/src/hooks/useWindowSize.ts) | ウィンドウサイズ取得 |

**設定**

| ファイル | 役割 |
|---|---|
| [frontend/src/config/api.ts](../frontend/src/config/api.ts) | API URL定数・静的ファイルパス |
| [frontend/src/config/api_client.ts](../frontend/src/config/api_client.ts) | axios共通クライアント |

**主要ライブラリ:** `react-pdf`, `tailwindcss`, `axios`, `react-router-dom`, `lucide-react`

---

## データディレクトリ構造 (backend/data/)

```
data/
├── main/
│   ├── pdfs/            ← 生成済みPDF
│   ├── pdfs_compressed/ ← 圧縮版PDF
│   ├── thumbnails/      ← サムネイル
│   ├── images/          ← 元WebP画像
│   └── complete/        ← 処理済みZIP/フォルダ
├── kindle/
│   ├── pdfs/ / thumbnails/ / images/
├── kindle_novel/
│   ├── pdfs/ / thumbnails/ / images/
└── meta/                ← 書籍メタデータ（作者名）
    ├── generated/meta.json
    ├── kindle/meta.json
    └── novel/meta.json
```

`source` パラメータ: `generated`(default) / `kindle` / `novel`

---

## Kindleキャプチャツール (kindle-pdf/)

| ファイル | 用途 |
|---|---|
| [kindle-pdf/main_auto.py](../kindle-pdf/main_auto.py) | 漫画自動キャプチャ |
| [kindle-pdf/main_manual.py](../kindle-pdf/main_manual.py) | 漫画手動キャプチャ |
| [kindle-pdf/main_novel.py](../kindle-pdf/main_novel.py) | 小説キャプチャ（画像保存のみ） |
| [kindle-pdf/batch_ocr.py](../kindle-pdf/batch_ocr.py) | バッチOCR → Searchable PDF生成 |

設計詳細: [kindle-pdf/docs/basic_design.md](../kindle-pdf/docs/basic_design.md)
