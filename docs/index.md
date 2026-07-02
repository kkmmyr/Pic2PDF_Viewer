# Pic2PDF_Viewer 設計ドキュメント

WebP 画像・ZIP を PDF 化してブラウザで閲覧する Web アプリ。Kindle キャプチャ連携 / OCR（yomitoku）による Searchable PDF 生成 / 小説テキスト検索・RAG 質問応答機能を提供する。

このサイトは `docs/` 配下の Markdown を **mkdocs-material** で HTML 化したもの。ソースは Markdown のままで、ビルド時に静的 HTML が生成される。Claude Code が読み書きするのは Markdown 側、ユーザーが閲覧するのが本 HTML 側、という役割分担。

---

## docs/ の 3 バケット構成

`docs/` 配下は役割ごとに 3 つのバケットに分かれている。個別ファイルへのリンクはこの index では持たない（サイドバー nav = `mkdocs.yml` の `nav:` が唯一のリンク一覧。二重管理はドリフトの元なので、ここでは各バケットの役割だけを説明する）。

### `design/` — 静的
要件定義・基本設計（ADR 含む）・詳細設計・環境構築などの設計書。仕様が変わった時だけ編集する。サイズは対象範囲（機能・アーキテクチャ）に応じて安定しており、無限には増えない。

### `log/` — 育つ運用ログ
変更履歴・既知の問題・技術知見・バックログ・リファクタリング計画書など、日々の開発で追記され続けるドキュメント。特に `log/変更履歴.md` は **pre-commit フック（`check-docs`）により 800 行以内に自動で制約**されており、超過すると古い週が `log/変更履歴/YYYY-Www.md` にローテーションされる（コミット時にブロックされるので、ローテーションを忘れたまま肥大化することはない）。

### `archive/` — 凍結
役目を終えた計画書・完了記録・撤去済み機能の要件定義など。原則として編集しない（過去の記録として保持）。`archive/変更履歴/`・`archive/要件/` 配下は個別に nav 掲載せず、変更履歴やバックログからの相互参照経由で辿る。

---

## 正本マップ（横断的な事実の所有文書）

複数の設計書に登場する横断的な事実は、下表の**所有文書だけが本文で定義**し、他の文書はそこへリンクする（同じ事実を二重に書かない — ドリフトの主因）。

| 事実 | 所有文書（正本） |
|---|---|
| プロジェクト全体のディレクトリ構成・3 バケットの役割 | 本 `index.md` ＋ `mkdocs.yml` の `nav`（個別ファイルのリンク一覧） |
| 開発/リリースのポート割当（8766 / 5176 / 8090）・リリースビルド構成・起動スクリプト | [詳細設計書_共通.md](design/詳細設計/詳細設計書_共通.md) §3 |
| source 3 値（doujin / comic / novel）・静的マウント・データディレクトリ配置 | [詳細設計書_共通.md](design/詳細設計/詳細設計書_共通.md) §2 |
| meta.db スキーマ（SQLModel / `MetaEntry`）・backend クラス設計 | [詳細設計書_バックエンド編.md](design/詳細設計/詳細設計書_バックエンド編.md) |
| API エンドポイント一覧・リクエスト/レスポンススキーマ | FastAPI `/openapi.json`・Swagger UI `/docs`（**手書きしない**）。OpenAPI で表せない設計意図のみ [API.md](design/詳細設計/API.md) |
| セキュリティ規約（`validate_safe_path` 等） | [セキュリティ設計書.md](design/詳細設計/セキュリティ設計書.md) |
| 小説 RAG の実機ベンチ・モデル選定・トラブルシュート | [小説RAG_技術知見.md](log/技術知見/小説RAG_技術知見.md) |
| 小説 RAG の DB スキーマ・`NOVEL_DB_*` 環境変数・LLM backend/port | 集約先を新設予定（機能別/小説RAG_データ.md）。それまでは [小説テキスト検索・RAG機能_バックエンド設計.md](design/詳細設計/機能別/小説テキスト検索・RAG機能_バックエンド設計.md) が正本 |

> 事実の二重記載を見つけたら、所有文書へ移してリンクへ置き換える。新しい横断的事実が生まれたら本表に所有文書を 1 つ決めて追記する。

---

## 整合性の自動チェック（ガバナンス）

`docs/**/*.md` または `mkdocs.yml` を変更するコミットは、pre-commit フック経由で `scripts/maintenance/check_docs.py` が検査する。ブロッキング違反（Rule 1/2/3/5）があるとコミットがブロックされ、Rule 4 は警告のみ：

1. **リンク切れ**（ブロック） — docs 間の相対 Markdown リンクが実在ファイルを指しているか
2. **変更履歴の肥大化**（ブロック） — `log/変更履歴.md` が上限 800 行を超えていないか（超過時は週次ローテーションを促す）
3. **nav 同期**（ブロック） — `mkdocs.yml` の nav ツリーが実ファイルと一致しているか（dead entry / orphan ファイルがないか）
4. **サイズ番犬**（warn・非ブロック） — `design/` 各設計書が 800 行を超えていないか（超過はまず設計過程・歴史の混在を疑う）
5. **status ヘッダ**（ブロック） — `design/` 各設計書の冒頭 10 行に `> status: living｜absorption-pending | last-verified: YYYY-MM-DD` があるか

さらに CI では `mkdocs build --strict` を独立した第二のチェックとして実行し、警告をエラー扱いにしてビルド段階でも壊れたリンクや設定ミスを検出する。

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

フロントエンドヘッダー右上の「設計書」リンクからも別タブで開ける（[`frontend/src/components/Layout.tsx`](../frontend/src/components/Layout.tsx)）。

---

## このサイトの位置づけ

- **ソース・オブ・トゥルース** は `docs/` 配下の Markdown（`design/` / `log/` / `archive/` の 3 バケット）
- **ユーザー閲覧用** は本 HTML（mkdocs build 出力）
- **編集**: Claude Code に依頼すると Markdown が更新される。次回 `mkdocs build` で HTML 反映
- **git 管理**: `docs/*.md` のみ。`frontend/public/site/` は `.gitignore`
