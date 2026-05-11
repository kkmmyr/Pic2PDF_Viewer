# Pic2PDF_Viewer 設計ドキュメント

WebP 画像・ZIP を PDF 化してブラウザで閲覧する Web アプリ。Kindle キャプチャ連携 / OCR（yomitoku）による Searchable PDF 生成 / 小説テキスト検索・RAG 質問応答機能を提供する。

このサイトは `docs/` 配下の Markdown を **mkdocs-material** で HTML 化したもの。ソースは Markdown のままで、ビルド時に静的 HTML が生成される。Claude Code が読み書きするのは Markdown 側、ユーザーが閲覧するのが本 HTML 側、という役割分担。

---

## 主要ドキュメント

### 01. 要件定義
- [要件定義書](01_要件定義/要件定義書.md) — システム全体の要件
- [小説テキスト検索・RAG機能](01_要件定義/小説テキスト検索・RAG機能.md) — novel タブの RAG 機能要件
- [機能追加候補](01_要件定義/機能追加候補.md) — バックログ A〜C ティア

### 02. 基本設計
- [ADR 一覧](02_基本設計/ADR/README.md) — 設計判断の記録（0001〜0007）

### 03. 詳細設計
- [バックエンド設計書](03_詳細設計/詳細設計書_バックエンド編.md)
- [フロントエンド設計書](03_詳細設計/詳細設計書_フロントエンド編.md)
- [API 仕様書](03_詳細設計/API仕様書.md)
- [OCR 設計書](03_詳細設計/OCR設計書.md)
- [小説 RAG バックエンド設計](03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md)
- [小説 RAG フロントエンド設計](03_詳細設計/小説テキスト検索・RAG機能_フロントエンド設計.md)
- [セキュリティ設計書](03_詳細設計/セキュリティ設計書.md)
- [ライセンス・コンプライアンス](03_詳細設計/ライセンス・コンプライアンス.md)

### 04. 環境構築
- [GPU環境セットアップ](04_環境構築/GPU環境セットアップ.md)

### 05. 記録
- [変更履歴](05_記録/変更履歴.md) — 全変更を時系列降順で記録
- [小説 RAG 技術知見](05_記録/小説RAG_技術知見.md) — 実機ベンチマーク / モデル選定 / トラブルシューティング
- [既知の問題](05_記録/既知の問題.md)

### 06. リファクタリング
- [リファクタリング計画書](06_リファクタリング/リファクタリング計画書.md) — 未着手・追加候補（slim）
- [リファクタリング履歴](06_リファクタリング/リファクタリング履歴.md) — 完了 Phase 1〜54 の詳細
- [テスト整備計画書（フロントエンド編）](06_リファクタリング/テスト整備計画書_フロントエンド編.md)

---

## ビルド方法

```powershell
# 単発ビルド（→ frontend/public/site/ に出力）
mkdocs build

# 開発時プレビュー（→ http://localhost:8000）
mkdocs serve
```

出力先は Vite の `publicDir`（`frontend/public/site/`）。これにより以下の経路すべてで閲覧可能:

| 経路 | URL |
|---|---|
| Vite dev (`npm run dev`) | `http://localhost:5176/site/index.html` |
| backend 直接（`/docs-html` マウント） | `http://localhost:8766/docs-html/` |
| リリース統合 (Vite dist 経由) | `http://localhost:8090/site/index.html` |
| リリース統合 (`/docs-html` 経由・後方互換) | `http://localhost:8090/docs-html/` |

フロントエンドヘッダー右上の「設計書」リンクからも別タブで開ける（[`frontend/src/components/Layout.tsx`](../../frontend/src/components/Layout.tsx)）。

---

## このサイトの位置づけ

- **ソース・オブ・トゥルース** は `docs/` 配下の Markdown
- **ユーザー閲覧用** は本 HTML（mkdocs build 出力）
- **編集**: Claude Code に依頼すると Markdown が更新される。次回 `mkdocs build` で HTML 反映
- **git 管理**: `docs/*.md` のみ。`frontend/public/site/` は `.gitignore`
