# Kindle キャプチャツール 基本設計書

## 1. システム概要

Windows 版「Kindle for PC」で開いている書籍を自動的にページめくりしながらスクリーンショットを撮影し、画像として保存する自動化ツール群。漫画用（`run_comic.bat`）と小説用（`run_novel.bat`）の 2 系統がある。

- **漫画（comic ソース）**: キャプチャ後に PDF を生成し `backend/data/comic/` へ保存。
- **小説（novel ソース）**: キャプチャした画像を `backend/data/kindle_novel/images/` へ保存のみ。OCR・PDF 生成・RAG インデックス構築は backend の job queue（`/novel/manage`）で実施する。

## 2. 動作環境

- **OS**: Windows 10/11
- **対象アプリ**: Kindle for PC
- **言語**: Python 3.x（`uv` で管理。`pyproject.toml` / `uv.lock`）
- **主な外部ライブラリ**:
    - `pyautogui`: キーボード・マウス操作
    - `pillow` (PIL): スクリーンショット取得
    - `opencv-python` (cv2): 画像保存・解析
    - `numpy`: 画像データ処理

## 3. 起動方法

```
kindle-pdf\run_comic.bat   # 漫画キャプチャ（main_auto.py を起動）
kindle-pdf\run_novel.bat   # 小説キャプチャ（main_novel.py を起動）
```

## 4. 機能概要

### 4.1. 漫画キャプチャ（フルスクリーン・自動検出モード）

- Kindle を F11 フルスクリーンに切り替えて撮影。
- 1 ページ目の画像を解析し、左右の黒帯（余白）を自動除去してコンテンツ領域を決定。
- 撮影後に画像をまとめて PDF 化し `backend/data/comic/pdfs/` に保存。

### 4.2. 小説キャプチャ（白背景検出モード）

- Kindle を F11 フルスクリーンに切り替えて撮影。
- 白背景（`WHITE_THRESHOLD = 240`）をもとにテキスト領域の左右端を自動検出。
- 画像のみ `backend/data/kindle_novel/images/<書籍名>/` に保存する（PDF 化・OCR はしない）。

## 5. ディレクトリ構成

```text
kindle-pdf/
├── capturer.py           # 基底クラス (Config, KindleCapturer, AutoConfig, AutoKindleCapturer)
├── main_manual.py        # 固定クロップモード（旧 main.py）
├── main_auto.py          # 漫画用フルスクリーン・自動検出モード
├── novel_capturer.py     # 小説用クラス (NovelConfig, NovelKindleCapturer)
├── main_novel.py         # 小説キャプチャ起動スクリプト
├── run_comic.bat         # 漫画キャプチャ起動（main_auto.py を呼び出す）
├── run_novel.bat         # 小説キャプチャ起動（main_novel.py を呼び出す）
├── pyproject.toml        # uv 依存管理
├── uv.lock               # uv ロックファイル
└── docs/
    ├── basic_design.md
    └── detailed_design.md
```

## 6. 入出力

| 系統 | 入力 | 出力 |
|---|---|---|
| 漫画 | Kindle for PC（開いた書籍） | 画像: `backend/data/comic/images/<書籍名>/` → PDF: `backend/data/comic/pdfs/<書籍名>.pdf` |
| 小説 | Kindle for PC（開いた書籍） | 画像のみ: `backend/data/kindle_novel/images/<書籍名>/` |

## 7. OCR・後処理フロー

漫画は capturer が直接 PDF を生成する。小説は画像保存のみで、後続処理は backend が担う。

```
[小説キャプチャ完了]
        ↓
backend/data/kindle_novel/images/<書籍名>/001.png ...
        ↓
/novel/manage（管理画面）から OCR ジョブをキュー投入
        ↓
yomitoku OCR → Searchable PDF → RAG インデックス構築
```
