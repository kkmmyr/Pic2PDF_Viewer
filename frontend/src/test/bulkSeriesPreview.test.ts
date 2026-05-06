/**
 * BulkSeriesAssignDialog の採番プレビューロジックのテスト（Phase 18-1）。
 *
 * 実際のコード (BulkSeriesAssignDialog.tsx):
 *   const start = mode === 'existing' && selected
 *       ? Math.floor(selected.maxIndex) + 1
 *       : 1;
 *   const previewIndexes = selectedNames.map((_, i) => start + i);
 *
 * 実行方法:
 *   cd frontend && npx vitest run src/test/bulkSeriesPreview.test.ts
 */
import { describe, it, expect } from 'vitest';

function calcPreviewIndexes(
    mode: 'existing' | 'new',
    maxIndex: number | undefined,
    count: number,
): number[] {
    const start = mode === 'existing' && maxIndex !== undefined ? Math.floor(maxIndex) + 1 : 1;
    return Array.from({ length: count }, (_, i) => start + i);
}

describe('BulkSeriesAssignDialog previewIndexes', () => {
    it('新規モードでは maxIndex に関わらず常に 1 から採番される', () => {
        expect(calcPreviewIndexes('new', undefined, 3)).toEqual([1, 2, 3]);
        expect(calcPreviewIndexes('new', 5, 3)).toEqual([1, 2, 3]);
        expect(calcPreviewIndexes('new', 0, 2)).toEqual([1, 2]);
    });

    it('既存モード・整数 maxIndex: maxIndex + 1 から採番される', () => {
        expect(calcPreviewIndexes('existing', 3, 3)).toEqual([4, 5, 6]);
        expect(calcPreviewIndexes('existing', 0, 2)).toEqual([1, 2]);
        expect(calcPreviewIndexes('existing', 10, 1)).toEqual([11]);
    });

    it('既存モード・小数 maxIndex: Math.floor した次の整数から採番される（小数巻対応）', () => {
        expect(calcPreviewIndexes('existing', 2.5, 3)).toEqual([3, 4, 5]);
        expect(calcPreviewIndexes('existing', 3.9, 2)).toEqual([4, 5]);
        expect(calcPreviewIndexes('existing', 1.1, 1)).toEqual([2]);
        // 2.9 → floor(2.9) = 2 → +1 = 3
        expect(calcPreviewIndexes('existing', 2.9, 2)).toEqual([3, 4]);
    });

    it('selectedNames が 1 冊の場合も正しく採番される', () => {
        expect(calcPreviewIndexes('new', undefined, 1)).toEqual([1]);
        expect(calcPreviewIndexes('existing', 4, 1)).toEqual([5]);
        expect(calcPreviewIndexes('existing', 4.5, 1)).toEqual([5]);
    });
});
