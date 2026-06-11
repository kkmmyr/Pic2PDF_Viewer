---
name: backend-conventions
description: backend/ 配下の Python/FastAPI コードを編集する際に発動。routers/services 分離、async/await、get_dirs_by_source、is_pdf_file/is_webp_file ユーティリティ、update_meta_locked パターン（既存フィールド保持）、validate_safe_path のセキュリティ規約、config パッケージ (pydantic-settings BaseSettings)、SQLModel + Alembic、response_model 必須を含む。
---

# バックエンド (Python / FastAPI) 規約

## 構成

- ルーターは `backend/routers/` に配置、ビジネスロジックは `backend/services/` に分離
- 非同期処理は `async/await` を使用
- データディレクトリの参照は `config.get_dirs_by_source()` を経由する。`source` パラメータの値は `doujin` / `comic` / `novel`
- 型ヒントを必ず付ける

## 設定 (config パッケージ)

- 設定は `config/` パッケージ（**pydantic-settings BaseSettings**）で管理する
    - アプリ設定（データパス・CORS 等）: `config/__init__.py`
    - Novel DB 設定（モデル・LLM・検索パラメータ等）: `config/novel_db.py`
- 設定値はライブ参照が必要なため `import config; config.X` を基本とする。ヘルパー関数・型（`get_dirs_by_source`, `SourceDirs`）は `from config import` 直 import 可
- 旧 `backend/config.py` 単一ファイル構成は廃止済み

## novel_db スキーマ

- モデル定義は **SQLModel**（`services/novel_db/models.py`）を使用する
- スキーマ変更は **Alembic が唯一の真実の源**（マイグレーションファイル追加）。手書き DDL 禁止

## API レスポンス

- 全エンドポイントに **`response_model` を付ける**。スキーマ定義は `routers/api_schemas.py`（フロントの openapi-typescript 型生成元）
- 新規エンドポイント追加後は frontend 側で `npm run generate:types` を実行して型を再生成する

## ユーティリティ強制

- ファイル拡張子チェックは `backend/utils/file_utils.py` の `is_pdf_file` / `is_webp_file` / `is_zip_file` / `is_image_file` を使用する。`name.lower().endswith('.xxx')` を直書きしない
- パスバリデーションは `utils/path_utils.py` の `validate_safe_path` / `validate_safe_name` を使用

## meta.json 更新の作法

- meta.json の更新は `services/meta_store.py` の `update_meta_locked(source, updater)` を使用し、`updater` 内で **既存フィールド（view_count / last_viewed_at 等）を保持** する形（`{**existing, "authors": [...]}`）で書く。エントリ全体を `{"authors": [a]}` で上書きしない

## 共通ルール（フロント・バック共通）

- コメントは「なぜ」が非自明な場合のみ記述する
- 不要なエラーハンドリングや将来の拡張を見越した抽象化はしない
- `source` パラメータ: `doujin` / `comic` / `novel`
