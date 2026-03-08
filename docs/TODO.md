# 今後の課題 (TODO)

ユーザー要望に基づく改善リストです。

## 1. OCR処理のCPU/GPU制御
- [x] **CPU利用の明示化**: OCR実行時 (`batch_ocr.py` 等)、GPUが利用できない場合はCPUを利用するように制御・ログ出力を明確にする（現在は自動フォールバックしているが、挙動を保証する）。
- [x] **GPU環境の調査**: `venv-gpu` 環境を構築し、CUDA対応のPyTorch + yomitokuを利用可能に。`backend/config.py` で自動検出。
- [ ] **OCRテキスト結合の改善** (Deferred)
  - **現状の問題**: 縦書き小説で単語が断片化（例: 「シルク」→「シル」+「ク」）
  - **検証結果 (2026-01-12)**:
    - `DocumentAnalyzer` API: 単語結合は改善したが、読み順が崩壊 → 不採用
    - 列ベースクラスタリング: 閾値ベースでは連鎖的に全て1列に結合 → 不採用
  - **今後の方針**: K-means/DBSCAN等の高度なクラスタリング、または yomitoku パラメータの詳細調査が必要
- [ ] **フリガナ除去の調整**: OCR処理結果にまだフリガナが残っている場合があるため、フィルタリングの閾値調整やロジック改善を行い、除去精度を向上させる。

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
