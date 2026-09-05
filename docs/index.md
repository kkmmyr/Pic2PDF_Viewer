# Pic2PDF_Viewer 設計ドキュメント

同人誌・漫画・小説を扱うマルチソース閲覧Webアプリ。WebP画像・ZIPの取り込みと
ブラウザ閲覧、Kindleキャプチャ連携、Surya OCR 2 + QAによる小説本文のSQLite公開、
bge-m3とQwenを使った全文検索・RAG質問応答を提供する。小説はSearchable PDFを生成せず、
原画像と`novel.db`の本文を分離して管理する。

このサイトは`docs/`配下のMarkdownを**mkdocs-material**でHTML化したもの。
Markdownを正本とし、HTMLは閲覧用の生成物とする。

## 最初に読む文書

| 知りたいこと | 参照先 |
|---|---|
| 現在できること・全体構成 | [要件定義書](design/要件定義/要件定義書.md) / [基本設計書](design/基本設計/基本設計書.md) |
| 現在の優先順位 | [バックログ](log/計画/バックログ.md) |
| 内部改善・技術メンテナンス | [リファクタリング計画書](log/計画/リファクタリング計画書.md) |
| 開発環境・配備・日常運用 | [uvセットアップ](design/環境構築/uv環境セットアップ.md) / [運用ガイド](design/環境構築/運用ガイド.md) |
| OCR改善・Sol導入の残作業 | [OCR計画](log/計画/小説OCR品質改善_実装計画.md) / [Sol導入計画](log/計画/Sol生成・評価_導入計画.md) |
| 現在発生している障害 | [既知の問題](log/既知の問題.md) |
| 設計書の置き場所・更新方法 | [設計書運用ルール](design/環境構築/設計書運用ルール.md) |
| 過去の試験・完了記録 | [アーカイブ索引](archive/index.md) / [変更履歴](log/変更履歴.md) |

---

## 文書の役割

- `design/`: 現在の要件・設計・運用契約。
- `log/`: 未完了計画、既知の問題、再利用する技術知見、変更履歴。
- `archive/`: 完了・中止した計画、過去の要件、検証記録。

このページは目的別の入口と正本一覧、サイドバーは分野別の目次として使う。
分類・状態・分割・検査のルールは[設計書運用ルール](design/環境構築/設計書運用ルール.md)を参照する。

<a id="canonical-map"></a>
## 正本マップ（横断的な事実の所有文書）

複数の設計書に登場する横断的な事実は、下表の**所有文書だけが本文で定義**し、他の文書はそこへリンクする（同じ事実を二重に書かない — ドリフトの主因）。

| 事実 | 所有文書（正本） |
|---|---|
| 文書の入口・分野別の目次 | 本`index.md` / `mkdocs.yml`の`nav` |
| 設計書の分類・状態・更新・archive移動・サイズ上限 | [設計書運用ルール](design/環境構築/設計書運用ルール.md) |
| 開発/リリースのポート割当・リリースビルドと配信構成 | [詳細設計書_共通.md](design/詳細設計/詳細設計書_共通.md) §3 |
| source 3 値（doujin / comic / novel）・静的マウント・データディレクトリ配置 | [詳細設計書_共通.md](design/詳細設計/詳細設計書_共通.md) §2 |
| meta2.db（SQLite `books_meta`）の責務・backend共通設計（schemaの正本は実装） | [詳細設計書_バックエンド編.md](design/詳細設計/詳細設計書_バックエンド編.md) |
| API エンドポイント一覧・リクエスト/レスポンススキーマ | FastAPI `/openapi.json`・Swagger UI `/docs`（**手書きしない**）。OpenAPI で表せない設計意図のみ [API.md](design/詳細設計/API.md) |
| セキュリティ規約（`validate_safe_path` 等） | [セキュリティ設計書.md](design/詳細設計/セキュリティ設計書.md) |
| 品質ゲート・baseline・例外・月次監査のルール | [品質ガードレール.md](design/詳細設計/品質ガードレール.md) |
| 互換facade・legacy migration・保守scriptの状態と再評価条件 | [保守資産・互換層台帳.md](design/環境構築/保守資産・互換層台帳.md) |
| 完了済みリファクタリングPhaseと検証実績 | [リファクタリング履歴.md](archive/リファクタリング履歴.md) |
| 日常運用・本番デプロイの判定基準・障害対応 | [運用ガイド.md](design/環境構築/運用ガイド.md) |
| サーバー操作のコピー用コマンド | [サーバー連携コマンド](design/環境構築/サーバー連携よく利用するコマンド.md) |
| Kindle自動撮影の利用者要件・受入条件 | [Kindle自動撮影取込_要件.md](design/要件定義/Kindle自動撮影取込_要件.md) |
| Kindle capture jobの状態遷移・排他・heartbeat・manifest・登録前検証境界 | [Kindle自動撮影ジョブ契約.md](design/詳細設計/機能別/Kindle自動撮影ジョブ契約.md) |
| Kindle Windows agentのクラス・処理順・実装パラメータ | `kindle-pdf/docs/detailed_design.md`（本サイト外の実装モジュール設計。横断契約を再定義しない） |
| Kindle実機で観測した制約・障害・復旧実績 | [Kindle自動撮影_実機知見.md](log/技術知見/Kindle自動撮影_実機知見.md)（契約は定義しない） |
| OCRの現行処理・QA・公開契約と品質指標の意味 | [OCR設計書.md](design/詳細設計/機能別/OCR設計書.md) |
| Mac / Windows Codex間のメッセージ、topic、比較文脈の中継契約 | [Codex端末間連携設計.md](design/詳細設計/機能別/Codex端末間連携設計.md) |
| OCR品質ゲートの機械判定値 | `scripts/maintenance/ocr_quality_policy.json`（説明と変更手順はOCR設計書） |
| OCR品質改善の未完了Phase・詳細な受入条件 | [小説OCR品質改善_実装計画.md](log/計画/小説OCR品質改善_実装計画.md)（[バックログ](log/計画/バックログ.md)は優先度と要約だけを所有） |
| 小説 RAG の実機ベンチ・モデル選定・トラブルシュート | [小説RAG_技術知見.md](log/技術知見/小説RAG_技術知見.md) |
| 小説 RAG の DB スキーマ・`NOVEL_DB_*` 環境変数・LLM backend/port | [小説RAG_データ.md](design/詳細設計/機能別/小説RAG_データ.md)（構築は [パイプライン設計](design/詳細設計/機能別/小説RAG_パイプライン設計.md)、検索/QA は [検索QA設計](design/詳細設計/機能別/小説RAG_検索QA設計.md)） |

> 事実の二重記載を見つけたら、所有文書へ移してリンクへ置き換える。新しい横断的事実が生まれたら本表に所有文書を 1 つ決めて追記する。

## 編集・検証・閲覧

- [文書の更新手順と正本の優先順位](design/環境構築/設計書運用ルール.md)
- [検証・HTMLビルド](design/環境構築/設計書運用ルール.md#docs-build)
- [アプリからのHTML配信構成](design/詳細設計/詳細設計書_共通.md)

Markdownを編集し、ビルドで閲覧用HTMLへ反映する。生成物の`frontend/public/site/`はGit管理しない。
