/**
 * useSeriesDrilldownReorder のユニットテスト。
 *
 * 回帰対象:
 * - バグ2 (stale state): 親から新しい books が渡されたら local state を再同期すること
 * - 項目18: 並び替え API 失敗時にロールバックしつつユーザーに toast.error で通知すること
 */
import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { toast } from 'sonner';
import type { DragEndEvent } from '@dnd-kit/core';

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('../features/novel_db/api', () => ({
    reorderNovelSeries: vi.fn(),
}));

import { reorderNovelSeries } from '@/features/novel_db/api';
import { useSeriesDrilldownReorder } from '@/hooks/novel_db/useSeriesDrilldownReorder';
import type { BookSummary } from '@/features/novel_db/types';

const mockedReorder = reorderNovelSeries as ReturnType<typeof vi.fn>;

const makeBook = (name: string): BookSummary => ({
    name,
    authors: [],
    series_id: 's1',
    series_title: 'テストシリーズ',
    is_indexed: false,
    page_count: null,
    indexed_at: null,
    thumbnail_url: null,
    ocr_done_at: null,
    volume: null,
    publisher: null,
    asin: null,
    series_index: null,
});

const makeDragEndEvent = (activeId: string, overId: string) =>
    ({
        active: { id: activeId },
        over: { id: overId },
    }) as unknown as DragEndEvent;

describe('useSeriesDrilldownReorder', () => {
    beforeEach(() => {
        mockedReorder.mockReset();
        (toast.error as ReturnType<typeof vi.fn>).mockReset();
    });

    it('親から渡された books の順序をそのまま初期表示する', () => {
        const books = [makeBook('a'), makeBook('b')];
        const onReordered = vi.fn();
        const { result } = renderHook(() => useSeriesDrilldownReorder('s1', books, onReordered));

        expect(result.current.books.map((b) => b.name)).toEqual(['a', 'b']);
    });

    it('バグ2: 親の books プロパティが変わったら local state を再同期する', () => {
        const onReordered = vi.fn();
        const { result, rerender } = renderHook(
            ({ books }: { books: BookSummary[] }) =>
                useSeriesDrilldownReorder('s1', books, onReordered),
            { initialProps: { books: [makeBook('a'), makeBook('b')] } },
        );

        expect(result.current.books.map((b) => b.name)).toEqual(['a', 'b']);

        // 他経路での編集後、親から新しい books（例: c が追加された）が渡されるケースを再現
        rerender({ books: [makeBook('a'), makeBook('b'), makeBook('c')] });

        expect(result.current.books.map((b) => b.name)).toEqual(['a', 'b', 'c']);
    });

    it('ドラッグ成功時: 楽観的に並び替え、API 成功後 onReordered が呼ばれる', async () => {
        mockedReorder.mockResolvedValue(undefined);
        const onReordered = vi.fn();
        const books = [makeBook('a'), makeBook('b'), makeBook('c')];
        const { result } = renderHook(() => useSeriesDrilldownReorder('s1', books, onReordered));

        await act(async () => {
            await result.current.handleDragEnd(makeDragEndEvent('a', 'c'));
        });

        expect(result.current.books.map((b) => b.name)).toEqual(['b', 'c', 'a']);
        expect(mockedReorder).toHaveBeenCalledWith('s1', ['b.pdf', 'c.pdf', 'a.pdf']);
        expect(onReordered).toHaveBeenCalledTimes(1);
        expect(toast.error).not.toHaveBeenCalled();
    });

    it('項目18: ドラッグ失敗時は元の順序にロールバックし toast.error で通知する', async () => {
        mockedReorder.mockRejectedValue(new Error('network error'));
        const onReordered = vi.fn();
        const books = [makeBook('a'), makeBook('b'), makeBook('c')];
        const { result } = renderHook(() => useSeriesDrilldownReorder('s1', books, onReordered));

        await act(async () => {
            await result.current.handleDragEnd(makeDragEndEvent('a', 'c'));
        });

        // ロールバックされ元の順序に戻る
        expect(result.current.books.map((b) => b.name)).toEqual(['a', 'b', 'c']);
        expect(onReordered).not.toHaveBeenCalled();
        expect(toast.error).toHaveBeenCalledTimes(1);
    });
});
