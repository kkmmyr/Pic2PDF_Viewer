---
name: frontend-conventions
description: frontend/src/ 配下の React/TypeScript コードを編集する際に発動。components 階層分離、apiClient 必須、Dialog/ConfirmDialog 共通シェル、validateFilename ユーティリティ、z-index Tailwind クラス、any 型禁止の規約を含む。
---

# フロントエンド (React / TypeScript) 規約

## 構成

- コンポーネントは `viewer/`（状態管理層）と `reader/`（プレゼンテーション層）に分離
- ロジックはカスタムフック (`hooks/`) に切り出す
- API URL は `frontend/src/config/api.ts` の定数を使用する
- API 呼び出しは `frontend/src/config/api_client.ts` の `apiClient` を使用する。`fetch` 直接呼び出し禁止
- `any` 型は原則使用しない

## ダイアログ・UI 共通プリミティブ

- ダイアログは `components/ui/Dialog.tsx` の共通シェル (`<Dialog>` / `DialogBody` / `DialogFooter` / `DialogCancelButton` / `DialogPrimaryButton`) を使用する。手書きの `fixed inset-0 bg-black/50 ...` 禁止
- ユーザー確認は `components/ui/ConfirmDialog.tsx` を使用する。`confirm()` / `alert()` 禁止（エラー通知は `useToast` のトーストを使う）
- ファイル名・フォルダ名のバリデーションは `utils/validation.ts` の `validateFilename(value, kind)` を使用する。各ダイアログで正規表現 `/[/\\:*?"<>|]/` を再定義しない

## スタイル

- z-index は Tailwind 任意値構文 (`z-[100]`) を避け、`tailwind.config.js` の階層クラスを使用する
    - `z-card-badge`（カード内バッジ）/ `z-overlay-bar`（ヘッダー下バー）/ `z-header`（ヘッダー）/ `z-toast` / `z-dialog` / `z-dialog-nested`
- マジックナンバーは `frontend/src/constants.ts` に集約する

## 共通ルール（フロント・バック共通）

- コメントは「なぜ」が非自明な場合のみ記述する
- 不要なエラーハンドリングや将来の拡張を見越した抽象化はしない

## 変更手順

ソースコードを修正する前に、必ず以下の順序で作業すること：

1. 関連する設計書（`docs/`配下）を更新する
2. `docs/05_記録/変更履歴.md` に変更内容を記録する
3. 設計書の更新を確認してからソースを修正する
