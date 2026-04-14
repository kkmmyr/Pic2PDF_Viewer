# 変更履歴 (CHANGELOG)

過去の主要な改善・リファクタリング作業の記録。

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
