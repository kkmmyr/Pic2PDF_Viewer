---
name: backend-conventions
description: backend/ 配下の Python/FastAPI コードを編集する際に発動。routers/services 分離、async/await、get_dirs_by_source、is_pdf_file/is_webp_file ユーティリティ、update_meta_locked パターン（既存フィールド保持）、validate_safe_path のセキュリティ規約を含む。
---

# バックエンド (Python / FastAPI) 規約

## 構成

- ルーターは `backend/routers/` に配置、ビジネスロジックは `backend/services/` に分離
- 非同期処理は `async/await` を使用
- データディレクトリの参照は `backend/config.py` の `get_dirs_by_source()` を経由する。`source` パラメータの値は `doujin` / `comic` / `novel`
- 型ヒントを必ず付ける

## ユーティリティ強制

- ファイル拡張子チェックは `backend/utils/file_utils.py` の `is_pdf_file` / `is_webp_file` / `is_zip_file` / `is_image_file` を使用する。`name.lower().endswith('.xxx')` を直書きしない
- パスバリデーションは `utils/path_utils.py` の `validate_safe_path` / `validate_safe_name` を使用

## meta.json 更新の作法

- meta.json の更新は `services/meta_store.py` の `update_meta_locked(source, updater)` を使用し、`updater` 内で **既存フィールド（view_count / last_viewed_at 等）を保持** する形（`{**existing, "authors": [...]}`）で書く。エントリ全体を `{"authors": [a]}` で上書きしない

## 共通ルール（フロント・バック共通）

- コメントは「なぜ」が非自明な場合のみ記述する
- 不要なエラーハンドリングや将来の拡張を見越した抽象化はしない
- `source` パラメータ: `doujin` / `comic` / `novel`
