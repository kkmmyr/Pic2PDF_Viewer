# Architecture Decision Records (ADR)

このプロジェクトの**設計判断の理由**を記録するディレクトリ。

「なぜこの技術／設計を選んだか」を残すことで、後から参画した人や数ヶ月後の自分が判断の妥当性を再評価できるようにする。コード・設計書・コミットメッセージから読み取れない**判断の根拠**を扱う。

## ファイル命名規則

`NNNN_短いタイトル.md` 形式。`NNNN` は連番 4 桁ゼロ埋め（例: `0001_react-vite-frontend.md`）。番号は採番後変更しない（リンクが壊れるため）。撤回・差し替えがあっても番号は残し、Status を `Superseded by ADR-NNNN` に書き換える。

## 一覧

| ID | タイトル | Status | 日付 |
|---|---|---|---|
| [0001](0001_react-vite-typescript-frontend.md) | フロントエンドに React + Vite + TypeScript を採用 | Accepted | 2026-01-12（遡及） |
| [0002](0002_fastapi-backend.md) | バックエンドに FastAPI を採用 | Accepted | 2026-01-12（遡及） |
| [0003](0003_generated-image-only-mode.md) | `generated` ソースを image-only モードに切替 | Accepted | 2026-05-05 |
| [0004](0004_hitomi-standalone-script.md) | hitomi 監視を独立スクリプト + Task Scheduler で実行 | Accepted | 2026-04-29 |
| [0005](0005_uv-python-package-manager.md) | Python パッケージ管理を `uv` に移行 | Accepted | 2026-04-26 |
| [0006](0006_backend-log-file-persistence.md) | バックエンドログを RotatingFileHandler でファイル永続化 | Accepted | 2026-05-07 |
| [0007](0007_llm-extraction-qwen-adoption.md) | 小説 RAG の LLM を Qwen3.6 に切替 + 共通モジュールに切り出し | Accepted | 2026-05-10 |
| [0008](0008_design-docs-html-build.md) | 設計ドキュメントを Markdown 編集 + mkdocs-material で HTML 配信 | Accepted | 2026-05-11 |
| [0009](0009_llm-backend-llama-server.md) | 小説 RAG の Qwen 推論バックエンドを Ollama から llama-server に切替 | Accepted | 2026-05-11 |
| [0010](0010_uv-workspace-monorepo.md) | uv workspace でモノレポ化（common/llm を repo 内に取り込み） | Accepted | 2026-06-11 |
| [0011](0011_github-actions-ci.md) | GitHub Actions CI 導入（PR 品質ゲートの自動化） | Accepted | 2026-06-11 |
| [0012](0012_sqlmodel-orm.md) | novel.db クエリを SQLModel ORM に移行 | Accepted | 2026-06-11 |
| [0013](0013_openapi-typescript.md) | openapi-typescript で BE/FE 型契約を一本化 | Accepted | 2026-06-11 |
| [0014](0014_react-router-data-router.md) | react-router v7 data router への移行 | Accepted | 2026-06-11 |
| — | _テンプレート: [0000_template.md](0000_template.md)_ | — | — |

## 新規 ADR 作成手順

1. `0000_template.md` をコピーし `NNNN_<タイトル>.md` にリネーム（NNNN は最新 +1）
2. すべてのフィールドを埋める（埋められない項目は「不明」と明記し、空欄は残さない）
3. 上記「一覧」テーブルに 1 行追加
4. 該当する設計書（要件定義 / 基本設計 / 詳細設計）からの相互参照リンクを追加検討

## 参考

- [Michael Nygard's ADR template](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) — 原典
