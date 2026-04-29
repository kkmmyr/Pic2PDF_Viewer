# フロントエンドテストパターン (vitest)

## フックのテスト: `renderHook`

```ts
import { renderHook } from '@testing-library/react';

const { result } = renderHook(() =>
    useLibraryFilter({ pdfs, directories, searchText: 'beta', ... })
);
expect(result.current.filteredPdfs).toEqual([...]);
```

- フックは `renderHook` で単体テスト
- API 呼び出しは `apiClient` を `vi.fn()` でモック（`useBookMeta.test.ts` 参照）

## コンポーネントのテストは原則書かない

- React コンポーネントの DOM 検証は工数対効果が悪い
- ロジックはフックに切り出してテストする方針（既存 `useEditMode` / `useSpreadMode` 等）
- ダイアログ等のインタラクションはユーザーが手動確認
