# 変更履歴 (CHANGELOG)

過去の主要な改善・リファクタリング作業の記録。

---

## 2026-04-14: 新機能追加 & MUI→Tailwind統一

### 概要
UX改善機能を4点実装し、フロントエンドのUIライブラリをMUI→TailwindCSS（Tailwind統一）に移行。

### 新機能

#### 1. PDF生成の非同期化 (Backend + Frontend)
- `backend/routers/pdfs.py`: `JobStore` / `GenerateJob` クラスを新設。UUIDジョブ管理 + スレッドセーフ設計。
- `POST /api/generate` → バックグラウンドスレッドで実行、`job_id` を即返却。
- `GET /api/generate/job/{job_id}` → ジョブ進捗ポーリングエンドポイントを追加。
- フロントエンド (`GeneratorPage.tsx`): 1500msポーリング、進捗UI（Clock/CheckCircle/XCircle アイコン、プログレスバー）。

#### 2. お気に入り / 並び替え
- `useFavorites.ts`: ソース別 `localStorage` 永続化。ソース切り替え時に自動再ロード。
- `useSortedPdfs.ts`: 5種類のソート順に対応 (`name_asc/desc`, `date_asc/desc`, `favorites_first`)。
- `LibraryPanel.tsx` / `LibraryHeader.tsx`: ソート順セレクタ追加 + localStorage永続化。
- `PdfGrid.tsx`: サムネイル左上に★ボタン追加。お気に入り状態をアンバー色で表示。
- `library.py`: `/api/pdfs` レスポンスに `created_at` (Unix timestamp) を追加。

#### 3. ダークモード
- `tailwind.config.js`: `darkMode: 'class'` 設定。
- `index.html`: React マウント前にインラインスクリプトで `<html class="dark">` 適用（フラッシュ防止）。
- `useDarkMode.ts`: `useState` 初期化時に即適用 + `localStorage` 永続化 + システムカラースキームフォールバック。
- 全コンポーネントに `dark:` クラスを適用。`Layout.tsx` にMoon/Sunトグルボタン追加。

#### 4. サムネイル遅延読み込み (Lazy Load)
- `LazyThumbnail.tsx`: `IntersectionObserver` (rootMargin 200px) でビューポート外のサムネイルを遅延読み込み。エラー時はFileTextアイコンにフォールバック。

#### 5. PDF内テキスト検索
- `PdfSearchBar.tsx`: Ctrl+F でサーチバーを開く。300msデバウンス入力、Enter/Shift+Enterで次/前移動、マッチ数表示。
- `ReaderPanel.tsx`: pdfjs で全ページテキストを走査してマッチカウント、`customTextRenderer` でハイライト表示。`renderTextLayer` は検索中のみ有効化（パフォーマンス最適化）。

### MUI→TailwindCSS統一
- `OCRPanel.tsx` / `OCRPage.tsx`: MUI `Box` / `Typography` / `Button` / `Chip` → Tailwindクラスに完全置き換え。`ThemeProvider` を削除。
- `CreateFolderDialog.tsx`: MUI `Dialog` → Tailwind固定オーバーレイ実装。バリデーション・Escクローズ・Enterサブミット・外クリックで閉じる。
- `package.json`: `@mui/material`, `@mui/icons-material`, `@emotion/react`, `@emotion/styled` を削除（約123パッケージ削減）。

---

## 2026-04-13: OCR品質改善

### 概要
縦書き小説OCR（yomitoku）の品質を改善。フリガナ除去・テキスト断片化・Searchable PDF生成の3点を修正。

### 主な変更

| ファイル | 内容 |
|---|---|
| `D:\61.tool\common\ocr\ocr_engine.py` | `_process_words` 実データ対応・aspect比判定追加 |
| `D:\61.tool\common\ocr\ocr_engine.py` | `filter_ruby_text` 自動閾値化（histogram valley検出） |
| `D:\61.tool\common\ocr\ocr_engine.py` | `_merge_text_fragments` Xビン分割方式に変更 |
| `D:\61.tool\common\ocr\ocr_engine.py` | `normalize_text` 追加（3点リーダー・特殊記号の正規化） |
| `kindle-pdf/searchable_pdf.py` | 縦書きテキストを1文字ずつ配置する方式に変更（長列の切れ問題を修正） |
| `D:\61.tool\common\ocr\debug_yomitoku.py` | yomitoku構造診断ツール（新規） |

詳細: [OCR_DESIGN.md](OCR_DESIGN.md)

---

## 2026-04-12: リファクタリング フェーズ4（品質向上・将来対応）

### 概要
テスト基盤整備・ErrorBoundary・フォルダ作成Dialog・環境変数整備。

### 主な変更
- `backend/tests/` ディレクトリ作成、pytest基盤整備
- `frontend/src/components/ErrorBoundary.tsx` 追加（アプリ全体をラップ）
- フォルダ作成UIを `window.prompt()` から MUI `Dialog` に変更
- `.env.example` 作成、`python-dotenv` 導入

---

## 2026-03-08: リファクタリング フェーズ1〜3

### フェーズ1: セキュリティ・安定性の修正 (Critical)
- `backend/utils/path_utils.py` 新規追加（パスバリデーション一元化）
- `GenerateState` / `OCRService` に `threading.Lock` 追加（スレッドセーフ化）
- `execute_moves()` にバックアップ→操作→リストアパターンを実装

### フェーズ2: 高優先度リファクタリング (High)
- `ViewerPage.tsx` をコンポーネント分割（`LibraryPanel` / `ReaderPanel` / `EditPanel`）
- `usePolling()` 共通フック作成（`usePdfStatus` / `useOcrStatus` の重複排除）
- `api_client.ts` にエラー種別定義・タイムアウト設定追加
- `pdf_generator.py` の重複ロジックを `_process_images()` に統合

### フェーズ3: コード品質向上 (Medium)
- TypeScript `any` 型を具体的な型に置き換え
- Pythonバックエンドに型ヒントを追加
- `print()` を `logging` モジュールに置き換え
- `config.py` のディレクトリ生成をループで統一

---

## 2026-01-12: Novel OCR 機能追加

### 概要
Kindle小説のSearchable PDF生成フローを確立。

### 主な変更
- `kindle-pdf/batch_ocr.py` 新規作成（バッチOCRスクリプト）
- `kindle-pdf/searchable_pdf.py` 新規作成（ReportLab透明テキストPDF生成）
- `frontend/src/pages/OCRPage.tsx` 追加（Web UIからOCR実行・監視）
- `backend/routers/ocr.py` 追加（OCR API）
- `backend/services/ocr_service.py` 追加（OCRプロセス管理）
- `kindle-pdf/main_novel.py` から重複PDF生成処理を削除
