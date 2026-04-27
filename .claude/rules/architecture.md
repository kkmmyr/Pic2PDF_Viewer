## バックエンド (FastAPI / Python)

| ファイル | 役割 |
|---|---|
| [backend/main.py](../../backend/main.py) | アプリ起動・ルーター登録・静的ファイルマウント |
| [backend/config.py](../../backend/config.py) | データディレクトリ定数・`get_dirs_by_source()` |
| [backend/routers/library.py](../../backend/routers/library.py) | ライブラリ一覧・フォルダ管理・移動・リネーム API |
| [backend/routers/pdfs.py](../../backend/routers/pdfs.py) | PDF 生成（非同期ジョブ）・ページ削除・圧縮・PDF 結合 API |
| [backend/routers/thumbnails.py](../../backend/routers/thumbnails.py) | サムネイル再生成 API（単発 / 一括） |
| [backend/routers/ocr.py](../../backend/routers/ocr.py) | OCR 実行・停止・ステータス API |
| [backend/routers/meta.py](../../backend/routers/meta.py) | 書籍メタデータ（作者名）取得・更新 API |
| [backend/services/pdf_service.py](../../backend/services/pdf_service.py) | PDFページ削除・ページ数取得ロジック |
| [backend/services/pdf_generator.py](../../backend/services/pdf_generator.py) | WebP/ZIP → PDF 変換（`scan_and_generate` / `batch_compress` / `_collect_images` 共通フロー） |
| [backend/services/thumbnail_service.py](../../backend/services/thumbnail_service.py) | サムネイル生成 |
| [backend/services/ocr_service.py](../../backend/services/ocr_service.py) | OCRバックグラウンドプロセス管理 |
| [backend/services/meta_store.py](../../backend/services/meta_store.py) | meta.json CRUD・ソース別ロック管理・`update_meta_locked()` |
| [backend/services/auto_fill_service.py](../../backend/services/auto_fill_service.py) | サークル名自動登録ジョブ管理（AutoFillState・スレッド起動） |
| [backend/utils/file_utils.py](../../backend/utils/file_utils.py) | 拡張子チェックユーティリティ（is_pdf_file / is_webp_file / is_zip_file / is_image_file） |

**主要ライブラリ:** `fastapi`, `uvicorn`, `img2pdf`, `Pillow`, `pymupdf`, `natsort`

---

## フロントエンド (React + TypeScript + Vite)

**ページ**

| ファイル | 役割 |
|---|---|
| [frontend/src/App.tsx](../../frontend/src/App.tsx) | ルーティング (`/viewer`, `/generator`, `/ocr`) |
| [frontend/src/pages/ViewerPage.tsx](../../frontend/src/pages/ViewerPage.tsx) | PDFライブラリ・リーダー統合ページ（LibraryProvider でラップするだけのシンプルな構造） |
| [frontend/src/pages/GeneratorPage.tsx](../../frontend/src/pages/GeneratorPage.tsx) | PDF生成ページ |
| [frontend/src/pages/OCRPage.tsx](../../frontend/src/pages/OCRPage.tsx) | Novel OCR実行ページ |

**コンポーネント (ui/ — 共通プリミティブ)**

| ファイル | 役割 |
|---|---|
| [frontend/src/components/ui/Dialog.tsx](../../frontend/src/components/ui/Dialog.tsx) | ダイアログ共通シェル（オーバーレイ + Esc/外クリック閉じ + Header/Body/Footer + ボタン） |
| [frontend/src/components/ui/ConfirmDialog.tsx](../../frontend/src/components/ui/ConfirmDialog.tsx) | 汎用確認ダイアログ（OS ネイティブ `confirm()` の置換用、危険操作対応） |

**コンポーネント (viewer/ — 状態管理層)**

| ファイル | 役割 |
|---|---|
| [frontend/src/components/viewer/LibraryPanel.tsx](../../frontend/src/components/viewer/LibraryPanel.tsx) | ライブラリUI（一覧・ソート・お気に入り・作者フィルター）props なし、LibraryContext から取得 |
| [frontend/src/components/viewer/ReaderPanel.tsx](../../frontend/src/components/viewer/ReaderPanel.tsx) | PDFリーダーUI（ページ表示・見開き制御・検索・削除） |
| [frontend/src/components/viewer/BulkAuthorDialog.tsx](../../frontend/src/components/viewer/BulkAuthorDialog.tsx) | 複数書籍への作者名一括設定ダイアログ（`<Dialog>` ベース） |
| [frontend/src/components/viewer/CreateFolderDialog.tsx](../../frontend/src/components/viewer/CreateFolderDialog.tsx) | フォルダ作成ダイアログ（`<Dialog>` ベース） |
| [frontend/src/components/viewer/RenameDialog.tsx](../../frontend/src/components/viewer/RenameDialog.tsx) | PDF/フォルダ共用リネームダイアログ（`<Dialog>` ベース） |
| [frontend/src/components/viewer/MergeDialog.tsx](../../frontend/src/components/viewer/MergeDialog.tsx) | PDF 結合ダイアログ（`<Dialog>` ベース） |
| [frontend/src/components/viewer/AutoFillAuthorsBar.tsx](../../frontend/src/components/viewer/AutoFillAuthorsBar.tsx) | サークル名自動登録バー（実行ボタン・モード選択・進捗表示） |

**コンポーネント (generator/ — PDF生成ページ用)**

| ファイル | 役割 |
|---|---|
| [frontend/src/components/generator/CompressionOptions.tsx](../../frontend/src/components/generator/CompressionOptions.tsx) | 圧縮版生成チェックボックス + 品質スライダー |
| [frontend/src/components/generator/JobProgress.tsx](../../frontend/src/components/generator/JobProgress.tsx) | PDF 生成ジョブの進捗パネル（pending/running/completed/failed） |
| [frontend/src/components/generator/StatusTable.tsx](../../frontend/src/components/generator/StatusTable.tsx) | 生成対象のステータス一覧表 |

**コンポーネント (reader/ — プレゼンテーション層)**

| ファイル | 役割 |
|---|---|
| [frontend/src/components/reader/ReaderHeader.tsx](../../frontend/src/components/reader/ReaderHeader.tsx) | リーダーヘッダー（見開きモード・方向・検索・編集ボタン） |
| [frontend/src/components/reader/PageRenderer.tsx](../../frontend/src/components/reader/PageRenderer.tsx) | 単一ページ描画（PDF/画像モード・ページサイズ通知） |
| [frontend/src/components/reader/LibraryHeader.tsx](../../frontend/src/components/reader/LibraryHeader.tsx) | ライブラリヘッダー（検索・ソート・作者フィルター・選択モード） |
| [frontend/src/components/reader/PdfGrid.tsx](../../frontend/src/components/reader/PdfGrid.tsx) | 書籍カードグリッド（サムネイル・作者名表示） |
| [frontend/src/components/reader/FolderGrid.tsx](../../frontend/src/components/reader/FolderGrid.tsx) | フォルダカードグリッド |
| [frontend/src/components/reader/PdfSearchBar.tsx](../../frontend/src/components/reader/PdfSearchBar.tsx) | PDF内テキスト検索バー |
| [frontend/src/components/reader/LazyThumbnail.tsx](../../frontend/src/components/reader/LazyThumbnail.tsx) | サムネイル遅延読み込み (IntersectionObserver) |
| [frontend/src/components/reader/MoveDialog.tsx](../../frontend/src/components/reader/MoveDialog.tsx) | 書籍移動ダイアログ |
| [frontend/src/components/reader/HeaderSearchBar.tsx](../../frontend/src/components/reader/HeaderSearchBar.tsx) | タイトル検索入力・作者フィルター選択 |
| [frontend/src/components/reader/HeaderSortSelect.tsx](../../frontend/src/components/reader/HeaderSortSelect.tsx) | ソート順選択ドロップダウン |
| [frontend/src/components/reader/SourceSelector.tsx](../../frontend/src/components/reader/SourceSelector.tsx) | ソース切り替えタブ（generated / kindle / novel） |
| [frontend/src/components/reader/ToastContainer.tsx](../../frontend/src/components/reader/ToastContainer.tsx) | トースト通知表示（右下固定・種別色分け） |

**カスタムフック (hooks/)**

| ファイル | 役割 |
|---|---|
| [frontend/src/hooks/useBookMeta.ts](../../frontend/src/hooks/useBookMeta.ts) | 書籍メタデータ（作者名）取得・更新・全作者集計 |
| [frontend/src/hooks/useLibraryManagement.ts](../../frontend/src/hooks/useLibraryManagement.ts) | ライブラリ操作（フォルダ作成・移動・リネーム） |
| [frontend/src/hooks/useReaderNavigation.ts](../../frontend/src/hooks/useReaderNavigation.ts) | ページナビゲーション（前/次・ジャンプ・リセット） |
| [frontend/src/hooks/useBookImages.ts](../../frontend/src/hooks/useBookImages.ts) | 書籍画像URL取得・画像モード判定 |
| [frontend/src/hooks/useImagePreloader.ts](../../frontend/src/hooks/useImagePreloader.ts) | 画像先読み |
| [frontend/src/hooks/useSortedPdfs.ts](../../frontend/src/hooks/useSortedPdfs.ts) | PDF一覧並び替え (useMemo) |
| [frontend/src/hooks/useFavorites.ts](../../frontend/src/hooks/useFavorites.ts) | お気に入り管理 (source別localStorage) |
| [frontend/src/hooks/useDarkMode.ts](../../frontend/src/hooks/useDarkMode.ts) | ダークモード管理 (localStorage永続化) |
| [frontend/src/hooks/useUrlState.ts](../../frontend/src/hooks/useUrlState.ts) | URLパラメータ同期 (path/file/source の読み書き) |
| [frontend/src/hooks/usePolling.ts](../../frontend/src/hooks/usePolling.ts) | 共通ポーリングフック |
| [frontend/src/hooks/usePdfStatus.ts](../../frontend/src/hooks/usePdfStatus.ts) | PDF生成ジョブ監視 |
| [frontend/src/hooks/useOcrStatus.ts](../../frontend/src/hooks/useOcrStatus.ts) | OCRステータス監視 |
| [frontend/src/hooks/useWindowSize.ts](../../frontend/src/hooks/useWindowSize.ts) | ウィンドウサイズ取得 |
| [frontend/src/hooks/useLibraryFilter.ts](../../frontend/src/hooks/useLibraryFilter.ts) | PDF/フォルダのフィルタリング（searchText / authorFilter / currentPath） |
| [frontend/src/hooks/usePdfSearch.ts](../../frontend/src/hooks/usePdfSearch.ts) | PDF テキスト検索（全ページ走査・マッチハイライト） |
| [frontend/src/hooks/useToast.ts](../../frontend/src/hooks/useToast.ts) | トースト通知管理（4秒自動消去） |
| [frontend/src/hooks/useSpreadMode.ts](../../frontend/src/hooks/useSpreadMode.ts) | 見開きモード（Auto/Spread/Single）の循環 + ページサイズによる Auto 判定 |
| [frontend/src/hooks/useEditMode.ts](../../frontend/src/hooks/useEditMode.ts) | リーダー編集モード（ページ選択・削除リクエスト・確認ダイアログ） |

**Context**

| ファイル | 役割 |
|---|---|
| [frontend/src/contexts/LibraryContext.tsx](../../frontend/src/contexts/LibraryContext.tsx) | ライブラリ状態一元管理（pdfs・選択モード・ダイアログ開閉・ナビゲーション）`LibraryProvider` + `useLibraryContext` |

**設定**

| ファイル | 役割 |
|---|---|
| [frontend/src/config/api.ts](../../frontend/src/config/api.ts) | API URL定数・静的ファイルパス |
| [frontend/src/config/api_client.ts](../../frontend/src/config/api_client.ts) | axios共通クライアント |
| [frontend/src/utils/validation.ts](../../frontend/src/utils/validation.ts) | ファイル名/フォルダ名バリデーション（`validateFilename` / `FORBIDDEN_FILENAME_CHARS`） |
| [frontend/src/utils/storage.ts](../../frontend/src/utils/storage.ts) | localStorage の JSON 読み書きユーティリティ |
| [frontend/tailwind.config.js](../../frontend/tailwind.config.js) | Tailwind 設定（z-index 階層: `z-card-badge` / `z-overlay-bar` / `z-header` / `z-toast` / `z-dialog` / `z-dialog-nested`） |

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
| [kindle-pdf/main_auto.py](../../kindle-pdf/main_auto.py) | 漫画自動キャプチャ |
| [kindle-pdf/main_manual.py](../../kindle-pdf/main_manual.py) | 漫画手動キャプチャ |
| [kindle-pdf/main_novel.py](../../kindle-pdf/main_novel.py) | 小説キャプチャ（画像保存のみ） |
| [kindle-pdf/batch_ocr.py](../../kindle-pdf/batch_ocr.py) | バッチOCR → Searchable PDF生成 |

設計詳細: [kindle-pdf/docs/basic_design.md](../../kindle-pdf/docs/basic_design.md)
