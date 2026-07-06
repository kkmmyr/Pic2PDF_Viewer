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
- import の使い分けは「**テストで差し替わる値か**」で決める（2026-07-06 裁定、直 import 26+ 箇所の実態を追認）:
    - **差し替わる値**（パス系定数 = `tests/conftest.py` の `paths` 一覧にある名前、および settings オブジェクトの属性）→ call-time 参照（`import config; config.X` / `app_settings.X` / `get_dirs_by_source()` 等の helper）。**新規コードでこれらを `from config import X` 直 import しない**（import 時にバインドされ monkeypatch が効かなくなる）
    - **静的値**（モデル名・閾値・`VALID_SOURCES` / `SUPPORTED_*` 等、テストで差し替えない値）→ `from config import X` 直 import 可。ヘルパー関数・型（`get_dirs_by_source`, `SourceDirs`）も直 import 可
    - 既存の例外: `main.py` の StaticFiles mount と `discussion_service.py` の `DISCUSSIONS_DIR` はパス定数を import 時にバインドするが、conftest が「patch → その後に main を import」の順序で成立させている（アプリ構築は本質的に import 時 1 回のため、記法変更では改善しない）。触らない
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

## meta.db 更新の作法

- 書籍メタデータの実体は **meta.db（SQLite、`services/meta_db.py`）**。更新は `services/meta_store.py`（meta.db の facade）の `update_meta_locked(source, updater)` を使用し、`updater` 内で **既存フィールド（view_count / last_viewed_at 等）を保持** する形（`{**existing, "authors": [...]}`）で書く。エントリ全体を `{"authors": [a]}` で上書きしない

## 共通ルール（フロント・バック共通）

- コメントは「なぜ」が非自明な場合のみ記述する
- 不要なエラーハンドリングや将来の拡張を見越した抽象化はしない
- `source` パラメータ: `doujin` / `comic` / `novel`
