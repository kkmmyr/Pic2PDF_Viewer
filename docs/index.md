# Pic2PDF_Viewer 設計ドキュメント

WebP 画像・ZIP を PDF 化してブラウザで閲覧する Web アプリ。Kindle キャプチャ連携 / OCR（yomitoku）による Searchable PDF 生成 / 小説テキスト検索・RAG 質問応答機能を提供する。

このサイトは `docs/` 配下の Markdown を **mkdocs-material** で HTML 化したもの。ソースは Markdown のままで、ビルド時に静的 HTML が生成される。Claude Code が読み書きするのは Markdown 側、ユーザーが閲覧するのが本 HTML 側、という役割分担。

---

## docs/ の 3 バケット構成

`docs/` 配下は役割ごとに 3 つのバケットに分かれている。個別ファイルへのリンクはこの index では持たない（サイドバー nav = `mkdocs.yml` の `nav:` が唯一のリンク一覧。二重管理はドリフトの元なので、ここでは各バケットの役割だけを説明する）。

### `design/` — 静的
要件定義・基本設計（ADR 含む）・詳細設計・環境構築などの設計書。仕様が変わった時だけ編集する。サイズは対象範囲（機能・アーキテクチャ）に応じて安定しており、無限には増えない。

### `log/` — 育つ運用ログ
変更履歴・既知の問題・技術知見・バックログ・リファクタリング計画書など、日々の開発で追記され続けるドキュメント。特に `log/変更履歴.md` は **pre-commit フック（`check-docs`）により 800 行以内に制約**されており、超過するとコミットをブロックして古い週を `log/変更履歴/YYYY-Www.md` へ手動ローテーションするよう促す。

### `archive/` — 凍結
役目を終えた計画書・完了記録・撤去済み機能の要件定義など。原則として編集しない（過去の記録として保持）。`archive/変更履歴/`・`archive/要件/` 配下は個別に nav 掲載せず、変更履歴やバックログからの相互参照経由で辿る。

---

<a id="canonical-map"></a>
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
| 品質ゲート・baseline・例外・月次監査のルール | [品質ガードレール.md](design/詳細設計/品質ガードレール.md) |
| 日常運用・本番デプロイの判定基準・障害対応 | [運用ガイド.md](design/環境構築/運用ガイド.md) |
| サーバー操作のコピー用コマンド | [サーバー連携コマンド](design/環境構築/サーバー連携よく利用するコマンド.md) |
| Kindle自動撮影の利用者要件・受入条件 | [Kindle自動撮影取込_要件.md](design/要件定義/Kindle自動撮影取込_要件.md) |
| Kindle capture jobの状態遷移・排他・heartbeat・manifest・登録前検証境界 | [Kindle購入カタログ設計.md](design/詳細設計/機能別/Kindle購入カタログ設計.md) |
| Kindle Windows agentのクラス・処理順・実装パラメータ | `kindle-pdf/docs/detailed_design.md`（本サイト外の実装モジュール設計。横断契約を再定義しない） |
| Kindle実機で観測した制約・障害・復旧実績 | [Kindle自動撮影_実機知見.md](log/技術知見/Kindle自動撮影_実機知見.md)（契約は定義しない） |
| OCRの現行処理・QA・公開契約と品質指標の意味 | [OCR設計書.md](design/詳細設計/機能別/OCR設計書.md) |
| OCR品質ゲートの機械判定値 | `scripts/maintenance/ocr_quality_policy.json`（説明と変更手順はOCR設計書） |
| OCR品質改善の未完了Phase・詳細な受入条件 | [小説OCR品質改善_実装計画.md](log/計画/小説OCR品質改善_実装計画.md)（[バックログ](log/計画/バックログ.md)は優先度と要約だけを所有） |
| 小説 RAG の実機ベンチ・モデル選定・トラブルシュート | [小説RAG_技術知見.md](log/技術知見/小説RAG_技術知見.md) |
| 小説 RAG の DB スキーマ・`NOVEL_DB_*` 環境変数・LLM backend/port・API 一覧 | [小説RAG_データ.md](design/詳細設計/機能別/小説RAG_データ.md)（構築は [パイプライン設計](design/詳細設計/機能別/小説RAG_パイプライン設計.md)、検索/QA は [検索QA設計](design/詳細設計/機能別/小説RAG_検索QA設計.md)） |

> 事実の二重記載を見つけたら、所有文書へ移してリンクへ置き換える。新しい横断的事実が生まれたら本表に所有文書を 1 つ決めて追記する。

### 正本が競合した場合の優先順位

1. OpenAPI、Alembic migration、OCR品質ポリシーなどの機械可読契約
2. `design/`の所有文書にある現在形の意味・境界・失敗時挙動
3. `log/計画/`の未完了作業と受入条件
4. `log/技術知見/`の実測・判断材料
5. `archive/`の完了時点または過去時点の記録

下位文書は上位の契約を上書きしない。差異を見つけた場合は、実装へ都合よく読み替えず、
所有文書と機械可読契約を照合してから修正する。`kindle-pdf/docs/`などMkDocs管理外の
モジュール文書も同様に、`docs/design/`の横断契約を再定義しない。

---

## 整合性の自動チェック（ガバナンス）

`docs/**/*.md`または`mkdocs.yml`を変更するコミットは、pre-commitフック経由で
`scripts/maintenance/check_docs.py`が検査する。次のRule 1〜6はすべてblockingである。

1. **リンク切れ**（ブロック） — living 文書の相対 Markdown リンクが実在ファイルを指しているか（`archive/` と週次変更履歴アーカイブの歴史的リンク切れは非ブロックの info 扱い — 過去の記録を doc 再編のたびに書き換えないため）
2. **変更履歴の肥大化**（ブロック） — `log/変更履歴.md` が上限 800 行を超えていないか（超過時は週次ローテーションを促す）
3. **nav 同期**（ブロック） — `mkdocs.yml` の nav ツリーが実ファイルと一致しているか（dead entry / orphan ファイルがないか）
4. **サイズ上限**（ブロック） — `design/`各設計書が800行を超えていないか（超過時は設計過程・歴史の混在と責務境界を確認する）
5. **status ヘッダ**（ブロック） — `design/` 各設計書の冒頭 10 行に `> status: living｜absorption-pending | last-verified: YYYY-MM-DD` があるか
6. **ファイルマップ注釈**（ブロック） — 自動生成ファイルマップの「主要ファイル補足」が実在パスを参照しているか

詳細な基準、baseline、例外管理は
[品質ガードレール](design/詳細設計/品質ガードレール.md)を正本とする。
さらにCIでは`mkdocs build --strict`を独立した第二のチェックとして実行する。

---

## ビルド方法

```powershell
# 単発ビルド（→ frontend/public/site/ に出力）
uv run mkdocs build --clean

# 開発時プレビュー（→ http://localhost:8000）
uv run mkdocs serve
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
