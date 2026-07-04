---
name: frontend-conventions
description: frontend/src/ 配下の React/TypeScript コードを編集する際に発動。components 階層分離（library/reader/novel_db/hitomi/ui）、@/ パスエイリアス強制、apiClient + TanStack Query 必須、openapi-typescript 生成型参照、sonner トースト、Dialog/ConfirmDialog 共通シェル（kebab-case）、z-index Tailwind クラス、any 型禁止の規約を含む。
---

# フロントエンド (React / TypeScript) 規約

## 構成

- コンポーネントは `components/{library, reader, novel_db, hitomi, ui}` に配置（旧 `viewer/` は `library/` にリネーム済）
- ロジックはカスタムフック `hooks/{library, novel_db, ...}` に切り出す
- import は **`@/` パスエイリアス**を使用する（相対 import `../` 禁止）。`tsconfig.app.json` paths + `vite.config.ts` alias で設定済み
- API URL は `@/config/api.ts` の定数を使用する
- API 呼び出しは `@/config/api_client.ts` の `apiClient` を使用する。`fetch` 直接呼び出し禁止
- `any` 型は原則使用しない

## データ取得

- データフェッチは **TanStack Query**（`useQuery` / `useMutation`）を使用する。`useState + useEffect` によるフェッチは禁止
- バックエンド由来の型は手書きせず **`src/types/api.d.ts`** を参照する（openapi-typescript 生成）
    - 再生成: backend を `:8766` で起動した状態で `npm run generate:types`（frontend/ ディレクトリで実行）

## ダイアログ・UI 共通プリミティブ

- UI プリミティブは `components/ui/` に置き、**個別ファイルを直接 import** する（`import { Dialog } from '@/components/ui/dialog'`。バレル index.ts は存在しない）
- 新規ファイル名は **kebab-case**（shadcn/ui CLI 規約: `confirm-dialog.tsx` 等）。⚠既存 7 ファイル（`Dialog.tsx` `Button.tsx` `Alert.tsx` 等）は PascalCase のまま残っており、import 側は小文字（`ui/dialog`）で書かれている — **Windows の大文字小文字非区別で偶然解決している潜在バグ**。case-sensitive 環境（Linux CI 等）ではビルドが壊れるため、これらへの import を書くときは既存記法（小文字）に合わせ、根本解消（kebab-case への git mv）は別作業として起票する
- ダイアログは `@/components/ui` の `<Dialog>` / `DialogBody` / `DialogFooter` / `DialogCancelButton` / `DialogPrimaryButton` を使用する。手書きの `fixed inset-0 bg-black/50 ...` 禁止
- ユーザー確認は `ConfirmDialog` を使用する。`confirm()` / `alert()` 禁止
- エラー通知は **sonner** の `toast()`（`import { toast } from 'sonner'`）を使用する。旧 `useToast` は廃止済み
- ファイル名・フォルダ名のバリデーションは `@/utils/validation.ts` の `validateFilename(value, kind)` を使用する。各ダイアログで正規表現を再定義しない

## スタイル

- z-index は Tailwind 任意値構文 (`z-[100]`) を避け、`frontend/src/index.css` の `@layer utilities` に定義したクラスを使用する（CSS 変数 `--z-*` で管理）
    - `z-card-badge`（カード内バッジ）/ `z-overlay-bar`（ヘッダー下バー）/ `z-header`（ヘッダー）/ `z-toast` / `z-dialog` / `z-dialog-nested`
- ダークモードは `html.dark` クラス切り替え方式。`index.css` に `@custom-variant dark (&:where(.dark, .dark *))` が定義済み
- マジックナンバーは `@/constants.ts` に集約する

## 関連 skill

- ソース変更時の設計書連動手順は `docs-workflow` skill が発動する
- 全体構成・設計書の場所は `architecture-overview` skill が発動する
