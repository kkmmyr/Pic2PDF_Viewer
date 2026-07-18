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

## コンポーネントのテスト: `render` + `fireEvent`

コンポーネントテストは多数存在する（`src/test/*.test.tsx` 約 28 本: `PdfCard` / `Dialog` / `GeneratorPage` 等）。

```tsx
import { render, fireEvent } from '@testing-library/react';

const { getByText } = render(<PdfCard {...baseProps} />);
expect(getByText('book')).toBeInTheDocument();
```

- 表示分岐・コールバック発火など**壊れやすい挙動**を `@testing-library/react` の `render` / `fireEvent` で検証（`PdfCard.test.tsx` 参照）
- ロジックはフックに切り出し、フック側は `renderHook` でテスト
- スナップショットテストは書かない（メンテコスト過大）
