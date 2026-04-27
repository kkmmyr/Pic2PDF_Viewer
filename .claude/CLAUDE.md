# プロジェクト設定

## 使用中のMCPサーバー

- **gemma-local** — ローカルのGemma 4:e4b モデル。コード説明・翻訳・生成・画像解析タスクをClaudeの代わりに処理してコストを節約する。ツール: ask_gemma / explain_code / generate_code / translate_text / analyze_image

利用基準の詳細は `D:\61.tool\Gemma 4\docs\gemma_tool_usage_guide.md` を参照すること。

---

## プロジェクト概要

WebP画像・ZIPをPDF化してブラウザで閲覧するWebアプリ。Kindleキャプチャ連携とOCR（yomitoku）によるSearchable PDF生成機能あり。

**設計書:**
- 要件: [docs/01_要件定義/要件定義書.md](../docs/01_要件定義/要件定義書.md)
- 基本設計: [docs/02_基本設計/基本設計書.md](../docs/02_基本設計/基本設計書.md)
- アーキテクチャ詳細: [docs/02_基本設計/アーキテクチャ詳細.md](../docs/02_基本設計/アーキテクチャ詳細.md) ← **コード変更タスクでは最初に Read で読み込む**
- 詳細設計: [docs/03_詳細設計/詳細設計書.md](../docs/03_詳細設計/詳細設計書.md)
- API: [docs/03_詳細設計/API仕様書.md](../docs/03_詳細設計/API仕様書.md)
- OCR: [docs/03_詳細設計/OCR設計書.md](../docs/03_詳細設計/OCR設計書.md)
- 変更履歴: [docs/05_記録/変更履歴.md](../docs/05_記録/変更履歴.md)

---

## 起動方法

```bash
# バックエンド（uv が依存解決と起動を一括実行）
cd backend && uv run uvicorn main:app --reload  # :8000

# フロントエンド
cd frontend && npm run dev  # :5173
```

Python パッケージ管理は **uv** を使用。`pyproject.toml` + `uv.lock` で依存を固定。

- 起動詳細: [起動方法.md](../起動方法.md)
- 環境構築: [docs/04_環境構築/uv環境セットアップ.md](../docs/04_環境構築/uv環境セットアップ.md)
