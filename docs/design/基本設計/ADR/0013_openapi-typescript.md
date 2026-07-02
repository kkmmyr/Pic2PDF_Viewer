# ADR-0013: openapi-typescript で BE/FE 型契約を一本化

- **Status**: Accepted
- **Date**: 2026-06-11
- **決定者**: 開発者
- **関連**: Phase 3-1 / commit `1215013` (BE) / `eee4417` (FE)

## コンテキスト

バックエンド（Pydantic スキーマ）とフロントエンド（手書き TypeScript 型）と API 仕様書（Markdown）の **3 箇所で型契約が独立管理**されていた。

- フロントの `BookSummary` が BE の `BookSummaryOut` と乖離してもコンパイルエラーにならない
- API 仕様書への追記忘れで仕様書が実態と乖離する事例が過去に複数回発生
- `openapi-typescript` 自体はすでに `package.json` の `devDependencies` 候補として認識されていたが、「工数大で対象外」と判断されていた（今回の大規模リファクタリングで解禁）

FastAPI は起動時に OpenAPI スキーマ（JSON）を自動生成する。`openapi-typescript` を使えば、そのスキーマから TypeScript の型定義を自動生成できる。

## 検討した選択肢

| 選択肢 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. 手書き型継続 | 変更なし | 乖離検知が手動のまま |
| B. tRPC | エンドツーエンド型安全な RPC フレームワーク | FastAPI を Python のままにする前提と相容れない |
| **C. openapi-typescript + FastAPI OpenAPI** | FastAPI の `/openapi.json` から TypeScript 型を自動生成 | （採用）既存 REST 構成を変えずに型安全性を獲得 |

## 決定

`backend/routers/api_schemas.py` を新規作成し、全 FastAPI エンドポイントに `response_model=` を付与して OpenAPI スキーマを完全化する。`openapi-typescript` で `src/types/api.d.ts` を自動生成し、手書き型の正確な一致箇所は `components['schemas']` の型エイリアスに置き換える。

精密さが失われる箇所（`field?: T | null` vs `field: T | null`）は手書き型を維持する。

## 根拠

- FastAPI の Pydantic モデルが唯一の真実の源となり、BE/FE 間の型乖離がビルド時に検出できる
- `response_model=` 付与により実行時レスポンス検証も強化される
- 手書き型を段階的に移行できる（完全一致箇所のみ置き換え）ため、破壊的変更リスクが低い
- `npm run generate:types` 1 コマンドで再生成でき、スキーマ変更に追従しやすい

## 結果（Consequences）

### ポジティブ
- `BookImagesResponse` / `MergePdfsResponse` など 9 型が自動生成型のエイリアスになり、BE 変更が FE 型エラーとして検出できる
- API 仕様書の手書きドキュメントは「人間向け説明」に専念できる（機械生成の型と役割分担）
- `generate:types` スクリプトが開発フローに組み込まれた

### ネガティブ・受容したコスト
- 型生成には backend を `:8766` で起動している必要がある（CI では別途起動ステップが必要）
- Pydantic の `Optional[T]` は OpenAPI で `field?: T | null` になり、実行時は常に存在するフィールドでも「省略可能」と表現される。この差は手書き型で吸収している
- `openapi-typescript@7.13.0` は TypeScript 5.x を peer require するため `--legacy-peer-deps` が必要（本プロジェクトは TS 6）

### 影響範囲
- `backend/routers/api_schemas.py`（新規 40+ Pydantic モデル）
- `frontend/src/types/api.d.ts`（自動生成、4700+ 行）
- `frontend/src/types/index.ts` / `frontend/src/features/novel_db/types.ts`（型エイリアス化）

## 将来の再評価条件

- `openapi-typescript` が TypeScript 6 に対応した場合は `--legacy-peer-deps` を外す
- CI に型生成と型チェックを自動化したい場合は、CI で `uvicorn` 起動 → `generate:types` → `tsc --noEmit` のステップを追加する
