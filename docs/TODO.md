# 今後の課題 (TODO)

ユーザー要望に基づく改善リストです。

## 1. OCR処理のCPU/GPU制御
- [x] **CPU利用の明示化**: OCR実行時 (`batch_ocr.py` 等)、GPUが利用できない場合はCPUを利用するように制御・ログ出力を明確にする（現在は自動フォールバックしているが、挙動を保証する）。
- [x] **GPU環境の調査**: `venv-gpu` 環境を構築し、CUDA対応のPyTorch + yomitokuを利用可能に。`backend/config.py` で自動検出。
- [x] **OCRテキスト結合の改善** (Completed 2026-04-13)
  - **調査結果**: yomitokuは断片化していなかった。縦書き各列がそのまま1 wordとして返る。
  - **対応**: X-binヒストグラム分割+aspect比判定による条件付きマージに変更（`D:\61.tool\common\ocr\ocr_engine.py`）
  - 詳細: [docs/OCR_IMPROVEMENT.md](OCR_IMPROVEMENT.md)
- [x] **フリガナ除去の調整** (Completed 2026-04-13)
  - ヒストグラム谷（valley）を自動検出して閾値を決定する方式に変更
  - ルビ(18-33px)と本文(38-48px)の間のギャップを確実に検出
  - 詳細: [docs/OCR_IMPROVEMENT.md](OCR_IMPROVEMENT.md)

## 2. Kindleキャプチャの改善
- [x] **不要なPDF出力の削除**: `kindle-pdf/main_novel.py` 実行時、最後に `capturer.create_pdf` が呼ばれており、`backend/data/kindle/pdfs` に画像PDFが生成されてしまう。Novelフローでは `batch_ocr.py` でSearchable PDF (`kindle_novel/pdfs`) を生成するため、この重複したPDF生成処理を削除する。

## 3. Web UI機能拡張
- [x] **OCR実行画面の追加**: Webビューア上に、LibraryやGeneratorと同じ階層で「Novel OCR」ページを追加する。
    - `frontend/src/pages/OCRPage.tsx` + `frontend/src/features/ocr/OCRPanel.tsx` として実装済み。
    - `/ocr` ルートにルーティング登録済み。
    - `batch_ocr.py` の実行・停止ボタン、コンソールログのリアルタイム表示機能を実装。

## 4. リファクタリング (Completed 2026-03-08)
- [x] **環境変数の導入**: フロントエンドの `.env` 対応。
- [x] **サービス層の抽出**: バックエンドロジックの整理（`PdfService`, `ThumbnailService`）。
- [x] **フロントエンドの共通化**: `apiClient` 導入とカスタムフックによるクリーンアップ。
