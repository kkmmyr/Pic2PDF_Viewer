## バックエンド (Python / FastAPI)

- ルーターは `backend/routers/` に配置、ビジネスロジックは `backend/services/` に分離
- 非同期処理は `async/await` を使用
- データディレクトリの参照は `backend/config.py` の `get_dirs_by_source()` を経由する
- 型ヒントを必ず付ける

## フロントエンド (React / TypeScript)

- コンポーネントは `viewer/`（状態管理層）と `reader/`（プレゼンテーション層）に分離
- ロジックはカスタムフック (`hooks/`) に切り出す
- API URLは `frontend/src/config/api.ts` の定数を使用する
- `any` 型は原則使用しない

## 変更手順

ソースコードを修正する前に、必ず以下の順序で作業すること：

1. 関連する設計書（`docs/`配下）を更新する
2. `docs/05_記録/変更履歴.md` に変更内容を記録する
3. 設計書の更新を確認してからソースを修正する

## 共通

- コメントは「なぜ」が非自明な場合のみ記述する
- 不要なエラーハンドリングや将来の拡張を見越した抽象化はしない
- `source` パラメータ: `generated` / `kindle` / `novel`
