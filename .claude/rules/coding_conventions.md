## バックエンド (Python / FastAPI)

- ルーターは `backend/routers/` に配置、ビジネスロジックは `backend/services/` に分離
- 非同期処理は `async/await` を使用
- データディレクトリの参照は `backend/config.py` の `get_dirs_by_source()` を経由する
- 型ヒントを必ず付ける
- ファイル拡張子チェックは `backend/utils/file_utils.py` の `is_pdf_file` / `is_webp_file` / `is_zip_file` / `is_image_file` を使用する。`name.lower().endswith('.xxx')` を直書きしない
- meta.json の更新は `services/meta_store.py` の `update_meta_locked(source, updater)` を使用し、`updater` 内で **既存フィールド（view_count / last_viewed_at 等）を保持** する形（`{**existing, "authors": [...]}`）で書く。エントリ全体を `{"authors": [a]}` で上書きしない
- パスバリデーションは `utils/path_utils.py` の `validate_safe_path` / `validate_safe_name` を使用

## フロントエンド (React / TypeScript)

- コンポーネントは `viewer/`（状態管理層）と `reader/`（プレゼンテーション層）に分離
- ロジックはカスタムフック (`hooks/`) に切り出す
- API URL は `frontend/src/config/api.ts` の定数を使用する
- API 呼び出しは `frontend/src/config/api_client.ts` の `apiClient` を使用する。`fetch` 直接呼び出し禁止
- `any` 型は原則使用しない

### ダイアログ・UI 共通プリミティブ

- ダイアログは `components/ui/Dialog.tsx` の共通シェル (`<Dialog>` / `DialogBody` / `DialogFooter` / `DialogCancelButton` / `DialogPrimaryButton`) を使用する。手書きの `fixed inset-0 bg-black/50 ...` 禁止
- ユーザー確認は `components/ui/ConfirmDialog.tsx` を使用する。`confirm()` / `alert()` 禁止（エラー通知は `useToast` のトーストを使う）
- ファイル名・フォルダ名のバリデーションは `utils/validation.ts` の `validateFilename(value, kind)` を使用する。各ダイアログで正規表現 `/[/\\:*?"<>|]/` を再定義しない

### スタイル

- z-index は Tailwind 任意値構文 (`z-[100]`) を避け、`tailwind.config.js` の階層クラスを使用する
    - `z-card-badge`（カード内バッジ）/ `z-overlay-bar`（ヘッダー下バー）/ `z-header`（ヘッダー）/ `z-toast` / `z-dialog` / `z-dialog-nested`
- マジックナンバーは `frontend/src/constants.ts` に集約する

## 変更手順

ソースコードを修正する前に、必ず以下の順序で作業すること：

1. 関連する設計書（`docs/`配下）を更新する
2. `docs/05_記録/変更履歴.md` に変更内容を記録する
3. 設計書の更新を確認してからソースを修正する

## 共通

- コメントは「なぜ」が非自明な場合のみ記述する
- 不要なエラーハンドリングや将来の拡張を見越した抽象化はしない
- `source` パラメータ: `generated` / `kindle` / `novel`

## テスト

- バックエンド: `cd backend && uv run pytest`（pytest）
- フロントエンド: `cd frontend && npm run test`（vitest）
- 新規ロジック追加時はテストを書く。特に副作用のあるロジック（meta.json 更新・ファイル移動・ジョブ管理）は必須
