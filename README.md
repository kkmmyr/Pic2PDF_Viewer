# Pic2PDF Viewer

同人誌・漫画・小説を扱う個人向けWebアプリ。WebP画像・ZIPの取り込みと閲覧、
Kindleキャプチャ連携、Surya OCR 2 + QAによる小説本文のSQLite公開、bge-m3 + Qwenによる
全文検索・RAG質問応答を備える。小説はSearchable PDFを生成せず、原画像と`novel.db`を分離する。

ローカルLAN・シングルユーザー向け。通常のブラウザ利用にユーザー認証は設けていない。
端末エージェントのトークン認証など、適用範囲は[セキュリティ設計書](docs/design/詳細設計/セキュリティ設計書.md)を参照する。

## 初回セットアップ

Pythonはuv workspace、Node.jsは[.node-version](.node-version)、npmは
[frontend/package.json](frontend/package.json)の`packageManager`に合わせる。

```bash
# リポジトリルートで実行
uv sync
cd frontend
npm ci
```

Python・OCRの依存管理は[uv環境セットアップ](docs/design/環境構築/uv環境セットアップ.md)、
GPUの追加設定は[GPU環境セットアップ](docs/design/環境構築/GPU環境セットアップ.md)、
Macでの開発は[Mac開発環境セットアップ](docs/design/環境構築/Mac開発環境セットアップ.md)を参照する。

## 起動・運用

Windowsの開発起動は`scripts/start.bat`。個別起動、Linux本番、Windowsローカルリリースの
使い分けは[起動方法](起動方法.md)、配備・バックアップ・障害対応は
[運用ガイド](docs/design/環境構築/運用ガイド.md)を参照する。

## 主要ディレクトリ

| パス | 役割 |
|---|---|
| `backend/` | FastAPIバックエンド（uv workspace member） |
| `frontend/` | React + TypeScript + Viteフロントエンド |
| `kindle-pdf/` | Kindleキャプチャ・OCRツール（uv workspace member） |
| `common/llm/` | 共通LLMクライアント（uv workspace member） |
| `scripts/` | 起動・配備・保守・検証スクリプト |
| `tools/` | バックアップ・データ移行ツール |
| `docs/` | 現行設計・計画・記録 |

## 設計書・開発ルール

- [設計書の入口・正本マップ](docs/index.md)
- [バックログ](docs/log/計画/バックログ.md) / [変更履歴](docs/log/変更履歴.md)
- [設計書の更新・検証・HTMLビルド](docs/design/環境構築/設計書運用ルール.md)
- [開発規約](AGENTS.md) / [Codex skills](.agents/skills/) / [Claude Code設定](.claude/)
- [ライセンス・コンプライアンス](docs/design/環境構築/ライセンス・コンプライアンス.md)
