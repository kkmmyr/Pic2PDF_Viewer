# Pic2PDF Viewer

同人誌・漫画・小説を扱う個人向けWebアプリケーション。WebP画像・ZIPの取り込みと閲覧、
Kindleキャプチャ連携、Surya OCR 2 + QAによる小説本文のSQLite公開、bge-m3 + Qwenによる
全文検索・RAG質問応答を備える。小説はSearchable PDFを生成せず、原画像と`novel.db`を分離する。

> **想定ユーザー**: ローカル LAN・シングルユーザー。認証は実装していない。LAN 外公開を想定する場合は別途設計が必要（[セキュリティ設計書 §1](docs/design/詳細設計/セキュリティ設計書.md)）

## 起動方法

### 開発モード（HMR 有効）

ダブルクリックで Backend (`:8766`) + Frontend (`:5176`) を Windows Terminal の別タブに自動起動:

```
scripts\start.bat
```

> 既に Backend が起動中の場合は再起動のみ実行する。Windows Terminal (`wt`) が未インストールの場合は手動で起動する:
> ```bash
> cd backend && uv run uvicorn main:app --reload --port 8766
> cd frontend && npm run dev
> ```

### リリースモード（フロントを統合配信、ポート `:8090`）

```
scripts\build_release.bat   :: 1. フロントをビルド
scripts\setup_service.bat   :: 2. 初回だけNSSMサービスを登録（管理者）
scripts\restart_service.bat :: 3. ビルド後にサービスを再起動
scripts\open_viewer.bat     :: 4. ブラウザを開く
```

Linux本番は`bash scripts/deploy_to_linux.sh`で世代デプロイする。詳細は[起動方法.md](起動方法.md)を参照する。

## 初回セットアップ

```bash
# uv workspace（backend / kindle-pdf / common/llm）
uv sync

# Frontend
cd frontend
npm install

# OCR を使う場合（GPU セットアップ）
uv sync --package pic2pdf-viewer-kindle --group gpu
```

詳細は [docs/design/環境構築/](docs/design/環境構築/) 配下:
- [uv環境セットアップ.md](docs/design/環境構築/uv環境セットアップ.md)
- [GPU環境セットアップ.md](docs/design/環境構築/GPU環境セットアップ.md)
- [運用ガイド.md](docs/design/環境構築/運用ガイド.md) — バックアップ・定期メンテナンス・トラブルシュート・性能指標

## 主要ディレクトリ

| パス | 役割 |
|---|---|
| `backend/` | FastAPI バックエンド（uv 管理 / Python 3.12+） |
| `frontend/` | React + TypeScript + Vite フロントエンド |
| `imagegen-catalog/` | 生成画像とプロンプト条件を持ち運び可能な形で閲覧する独立 React + FastAPI アプリ |
| `kindle-pdf/` | Kindle キャプチャ + OCR ツール（独立 uv プロジェクト） |
| `docs/` | 設計書・ADR・運用ガイド・変更履歴 |
| `tools/` | バックアップ・データ移行スクリプト |
| `.claude/` | Claude Code 設定（skill / hook / slash command） |

## ドキュメント

| 領域 | 入口 |
|---|---|
| 全体像 | [docs/design/基本設計/基本設計書.md](docs/design/基本設計/基本設計書.md) |
| 設計書の読み方・正本 | [docs/index.md](docs/index.md) |
| 設計書運用ルール | [設計書運用ルール.md](docs/design/環境構築/設計書運用ルール.md) |
| バックログ | [docs/log/計画/バックログ.md](docs/log/計画/バックログ.md) |
| 設計判断の理由 (ADR) | [docs/design/基本設計/ADR/](docs/design/基本設計/ADR/) |
| 詳細設計（バックエンド） | [詳細設計書_バックエンド編.md](docs/design/詳細設計/詳細設計書_バックエンド編.md) |
| 詳細設計（フロントエンド） | [詳細設計書_フロントエンド編.md](docs/design/詳細設計/詳細設計書_フロントエンド編.md) |
| API 仕様 | [docs/design/詳細設計/API.md](docs/design/詳細設計/API.md)（一覧は /openapi.json） |
| セキュリティ | [docs/design/詳細設計/セキュリティ設計書.md](docs/design/詳細設計/セキュリティ設計書.md) |
| ライセンス・コンプライアンス | [docs/design/環境構築/ライセンス・コンプライアンス.md](docs/design/環境構築/ライセンス・コンプライアンス.md) |
| 変更履歴 | [docs/log/変更履歴.md](docs/log/変更履歴.md) |

## 開発支援

共通の開発規約は[AGENTS.md](AGENTS.md)、Codex skillは[.agents/skills/](.agents/skills/)、
Claude Code固有設定は[.claude/](.claude/)を参照する。設計書の機械検査は
`uv run python scripts/maintenance/check_docs.py`で実行する。

## 開発フロー

設計の意図に関わる変更は[設計書運用ルール](docs/design/環境構築/設計書運用ルール.md)に従い、以下の順序で進める。

1. **設計書を更新** — `docs/<該当領域>/...md`（要件定義 / 基本設計 / 詳細設計 / アーキテクチャ詳細 / API 仕様 / セキュリティ / OCR 等）
2. **変更履歴に追記** — [docs/log/変更履歴.md](docs/log/変更履歴.md) の「直近の追記」先頭に `## YYYY-MM-DD: type — タイトル` を追加（`/changelog` で草稿生成可）
3. **ソースを修正** — backend / frontend / kindle-pdf
4. **テスト・リント** — `uv run pytest` / `npm run test` / `uv run ruff check` / `npm run lint`
5. **コミット** — Conventional Commits（`feat:` / `fix:` / `refactor:` / `docs:` / `test:` / `chore:`）+ HEREDOC で Co-Authored-By trailer 付与

軽微な変更（typo・コメント整理・スタイルのみ）は設計書更新を省略できる。完了・中止した計画は同じ変更で`docs/archive/`へ移す。

## ライセンス

未指定（個人プロジェクト）。配布する場合は依存ライブラリのライセンス（特に PyMuPDF AGPL-3.0）に準拠した LICENSE ファイル明記が必要。詳細は [docs/design/環境構築/ライセンス・コンプライアンス.md](docs/design/環境構築/ライセンス・コンプライアンス.md)。
