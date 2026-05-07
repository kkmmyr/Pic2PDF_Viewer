# Pic2PDF Viewer

WebP 画像・ZIP を PDF 化してブラウザで閲覧する個人向け Web アプリケーション。Kindle キャプチャ連携と OCR (yomitoku) による Searchable PDF 生成機能あり。

> **想定ユーザー**: ローカル LAN・シングルユーザー。認証は実装していない。LAN 外公開を想定する場合は別途設計が必要（[セキュリティ設計書 §1](docs/03_詳細設計/セキュリティ設計書.md)）

## 起動方法

### 開発モード（HMR 有効）

ダブルクリックで Backend (`:8766`) + Frontend (`:5176`) を Windows Terminal の別タブに自動起動:

```
start.bat
```

> 既に Backend が起動中の場合は再起動のみ実行する。Windows Terminal (`wt`) が未インストールの場合は手動で起動する:
> ```bash
> cd backend && uv run uvicorn main:app --reload --port 8766
> cd frontend && npm run dev
> ```

### リリースモード（フロントを統合配信、ポート `:8090`）

```
build_release.bat   :: 1. フロントをビルド (frontend/dist/)
start_release.bat   :: 2. backend/main.py が dist/ を /  に static mount で配信
```

ブラウザは自動起動、5 秒間隔の restart loop 付き。

## 初回セットアップ

```bash
# Backend (uv 必須)
cd backend
uv sync

# Frontend
cd frontend
npm install

# OCR を使う場合（GPU セットアップ）
cd kindle-pdf
uv sync --group gpu
```

詳細は [docs/04_環境構築/](docs/04_環境構築/) 配下:
- [uv環境セットアップ.md](docs/04_環境構築/uv環境セットアップ.md)
- [GPU環境セットアップ.md](docs/04_環境構築/GPU環境セットアップ.md)
- [運用ガイド.md](docs/04_環境構築/運用ガイド.md) — バックアップ・定期メンテナンス・トラブルシュート・性能指標

## 主要ディレクトリ

| パス | 役割 |
|---|---|
| `backend/` | FastAPI バックエンド（uv 管理 / Python 3.12+） |
| `frontend/` | React + TypeScript + Vite フロントエンド |
| `kindle-pdf/` | Kindle キャプチャ + OCR ツール（独立 uv プロジェクト） |
| `docs/` | 設計書・ADR・運用ガイド・変更履歴 |
| `tools/` | バックアップ・データ移行スクリプト |
| `.claude/` | Claude Code 設定（skill / hook / slash command） |

## ドキュメント

| 領域 | 入口 |
|---|---|
| 全体像 | [docs/02_基本設計/基本設計書.md](docs/02_基本設計/基本設計書.md) |
| 設計判断の理由 (ADR) | [docs/02_基本設計/ADR/](docs/02_基本設計/ADR/) |
| 詳細設計（バックエンド） | [docs/02_基本設計/アーキテクチャ詳細_バックエンド編.md](docs/02_基本設計/アーキテクチャ詳細_バックエンド編.md) → [詳細設計書_バックエンド編.md](docs/03_詳細設計/詳細設計書_バックエンド編.md) |
| 詳細設計（フロントエンド） | [docs/02_基本設計/アーキテクチャ詳細_フロントエンド編.md](docs/02_基本設計/アーキテクチャ詳細_フロントエンド編.md) → [詳細設計書_フロントエンド編.md](docs/03_詳細設計/詳細設計書_フロントエンド編.md) |
| API 仕様 | [docs/03_詳細設計/API仕様書.md](docs/03_詳細設計/API仕様書.md) |
| セキュリティ | [docs/03_詳細設計/セキュリティ設計書.md](docs/03_詳細設計/セキュリティ設計書.md) |
| ライセンス・コンプライアンス | [docs/03_詳細設計/ライセンス・コンプライアンス.md](docs/03_詳細設計/ライセンス・コンプライアンス.md) |
| 変更履歴 | [docs/05_記録/変更履歴.md](docs/05_記録/変更履歴.md) |

## 開発支援

Claude Code 用の設定は [.claude/](.claude/) を参照。スラッシュコマンド一覧:

```
/big-files       肥大化候補ファイル上位 10 件
/audit           npm audit + uv audit
/check-docs      設計書と実装の整合性クロスチェック
/refactor-status リファクタリング計画書の状態サマリ
/changelog       直近コミットから変更履歴追記の草稿生成
/sync-memory     永続メモリと実態のズレ修正
```

## 開発フロー

設計の意図に関わる変更は以下の順序で進める（[.claude/skills/docs-workflow/SKILL.md](.claude/skills/docs-workflow/SKILL.md) で Claude にも自動案内される）:

1. **設計書を更新** — `docs/<該当領域>/...md`（要件定義 / 基本設計 / 詳細設計 / アーキテクチャ詳細 / API 仕様 / セキュリティ / OCR 等）
2. **変更履歴に追記** — [docs/05_記録/変更履歴.md](docs/05_記録/変更履歴.md) の「直近の追記」先頭に `## YYYY-MM-DD: type — タイトル` を追加（`/changelog` で草稿生成可）
3. **ソースを修正** — backend / frontend / kindle-pdf
4. **テスト・リント** — `uv run pytest` / `npm run test` / `uv run ruff check` / `npm run lint`
5. **コミット** — Conventional Commits（`feat:` / `fix:` / `refactor:` / `docs:` / `test:` / `chore:`）+ HEREDOC で Co-Authored-By trailer 付与

軽微な変更（typo・コメント整理・スタイルのみ）は設計書更新を省略可。詳細は [.claude/skills/git-workflow/SKILL.md](.claude/skills/git-workflow/SKILL.md) と [.claude/skills/docs-workflow/SKILL.md](.claude/skills/docs-workflow/SKILL.md)。

## ライセンス

未指定（個人プロジェクト）。配布する場合は依存ライブラリのライセンス（特に PyMuPDF AGPL-3.0）に準拠した LICENSE ファイル明記が必要。詳細は [docs/03_詳細設計/ライセンス・コンプライアンス.md](docs/03_詳細設計/ライセンス・コンプライアンス.md)。
