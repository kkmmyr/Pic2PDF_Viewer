# ADR-0014: react-router v7 data router への移行

- **Status**: Accepted
- **Date**: 2026-06-11
- **決定者**: 開発者
- **関連**: Phase 2-2 / commit `e4db7e0`

## コンテキスト

`react-router-dom@7.17.0` を導入済みだったが、`<BrowserRouter>` + `<Routes>` の **v6 流儀のみ**を使っていた。data router の主要機能（`createBrowserRouter` / `loader` / `action` / `errorElement`）を 0 箇所利用。

主な問題：

- `useEffect` + fetch でデータ取得するページが複数あり、`react-hooks/exhaustive-deps` 違反を `eslint-disable` で抑制していた
- 各ページに手動で `<ErrorBoundary>` を入れ子にしており、エラー処理が分散していた
- コード分割（`React.lazy`）が `NovelGraphPage` 1 ページのみで、初回バンドルが大きかった

## 検討した選択肢

| 選択肢 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. v6 流儀を維持 | 変更なし | ESLint 違反の放置・ErrorBoundary 分散が続く |
| B. Tanstack Router 移行 | 型安全なルーティングライブラリ | react-router v7 が既に導入済みで移行コストが大きい |
| **C. createBrowserRouter + data router** | react-router v7 の推奨 API に移行 | （採用）ライブラリを追加せず v7 機能を活用 |

## 決定

`createBrowserRouter` にルートを移行し、`errorElement` で共通エラー表示を統一する。全ページ（9 本）を `React.lazy` + `Suspense` でコード分割し、`lazyPages.tsx` に集約する。

## 根拠

- `errorElement` で各ルートの手書き `<ErrorBoundary>` を除去でき、`ErrorBoundary.tsx` 自体を削除できた
- 全ページ lazy 化で初回バンドルが分割され、使わないページのコードが遅延ロードされる
- `createBrowserRouter` への移行が react-router v7 のベストプラクティスであり、将来の v8 対応コストを下げる

## 結果（Consequences）

### ポジティブ
- `ErrorBoundary.tsx` 削除（各ページの `<ErrorBoundary>` 手動ラップが不要）
- 全 9 ページが `React.lazy` でコード分割され、初回バンドル縮小
- `eslint-disable react-hooks/set-state-in-effect` の根本原因が一部解消
- `RouteErrorPage` として統一されたエラー UI が全ルートで動作

### ネガティブ・受容したコスト
- `loader` / `action` API は今回未活用（ページ内 TanStack Query が担当）。data router のフルポテンシャルは引き出せていない
- `React.lazy` によりページ初回表示に `<Suspense>` フォールバック（ローディング）が挟まる

### 影響範囲
- `frontend/src/App.tsx`（`createBrowserRouter` ベースに全面書き換え）
- `frontend/src/lazyPages.tsx`（新規：全ページの lazy インポートを集約）
- `frontend/src/pages/RouteErrorPage.tsx`（新規）
- `frontend/src/components/ErrorBoundary.tsx`（削除）

## 将来の再評価条件

- TanStack Query との役割分担を見直し、`loader` でプリフェッチを行う場合は本 ADR を更新する
- react-router v8 でブレーキングチェンジがあった場合に本 ADR を Superseded にする

## 修正（2026-06-12）

commit `957ac7c` で `ErrorBoundary.tsx` を class component として再追加し、`Layout.tsx` の `<Outlet>` をラップする形で復活させた。

**理由**: data router の `errorElement` はルートレベルのエラー（ナビゲーション失敗・loader 例外）のみをキャッチする。レンダリング中の予期しない React エラー（`null` デリファレンス等）は `errorElement` ではキャッチされないことが判明し、`ErrorBoundary` が必要になった。

**結果**: 本 ADR の「`ErrorBoundary.tsx` 削除」という記述は撤回。`ErrorBoundary.tsx` と `RouteErrorPage.tsx` は**両方**共存する。
- `ErrorBoundary.tsx`（class component）: レンダリングエラーをキャッチし fallback UI を表示
- `RouteErrorPage.tsx`: ルートレベルエラーの共通 UI
