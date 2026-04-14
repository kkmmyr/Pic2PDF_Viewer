# グローバル設定

## 使用中のMCPサーバー

- **gemma-local** — ローカルのGemma 4:e4b モデル。コード説明・翻訳・生成・画像解析タスクをClaudeの代わりに処理してコストを節約する。ツール: ask_gemma / explain_code / generate_code / translate_text / analyze_image

利用基準の詳細は `D:\61.tool\Gemma 4\docs\gemma_tool_usage_guide.md` を参照すること。


---

## プロジェクト概要

WebP画像・ZIPをPDF化してブラウザで閲覧するWebアプリ。Kindleキャプチャ連携とOCR（yomitoku）によるSearchable PDF生成機能あり。

- 要件: [docs/REQUIREMENTS.md](../docs/REQUIREMENTS.md)
- 設計: [docs/BASIC_DESIGN.md](../docs/BASIC_DESIGN.md) / [docs/DETAILED_DESIGN.md](../docs/DETAILED_DESIGN.md)
- API: [docs/API_SPEC.md](../docs/API_SPEC.md)
- OCR: [docs/OCR_DESIGN.md](../docs/OCR_DESIGN.md)
- 変更履歴: [docs/CHANGELOG.md](../docs/CHANGELOG.md)

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
| [backend/routers/library.py](../backend/routers/library.py) | ライブラリ一覧API |
| [backend/routers/pdfs.py](../backend/routers/pdfs.py) | PDF生成・閲覧・ページ削除API |
| [backend/routers/ocr.py](../backend/routers/ocr.py) | OCR実行・停止API |
| [backend/services/pdf_service.py](../backend/services/pdf_service.py) | PDFスキャン・閲覧ロジック |
| [backend/services/pdf_generator.py](../backend/services/pdf_generator.py) | WebP/ZIP → PDF変換 |
| [backend/services/thumbnail_service.py](../backend/services/thumbnail_service.py) | サムネイル生成 |

**主要ライブラリ:** `fastapi`, `uvicorn`, `img2pdf`, `Pillow`, `pymupdf`, `natsort`

### フロントエンド (React + TypeScript + Vite)

| ファイル | 役割 |
|---|---|
| [frontend/src/App.tsx](../frontend/src/App.tsx) | ルーティング (`/viewer`, `/generator`, `/ocr`) |
| [frontend/src/config/api_client.ts](../frontend/src/config/api_client.ts) | axios共通クライアント |
| [frontend/src/pages/ViewerPage.tsx](../frontend/src/pages/ViewerPage.tsx) | PDFライブラリ・リーダー画面 |
| [frontend/src/pages/GeneratorPage.tsx](../frontend/src/pages/GeneratorPage.tsx) | PDF生成画面 |
| [frontend/src/pages/OCRPage.tsx](../frontend/src/pages/OCRPage.tsx) | Novel OCR実行画面 |
| [frontend/src/hooks/](../frontend/src/hooks/) | カスタムフック群 |

**主要ライブラリ:** `react-pdf`, `@mui/material`, `tailwindcss`, `axios`, `react-router-dom`

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
└── kindle_novel/
    ├── pdfs/ / thumbnails/ / images/
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
