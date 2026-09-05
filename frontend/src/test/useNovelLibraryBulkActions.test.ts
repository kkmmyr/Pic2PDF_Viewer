import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from 'sonner';

import { useNovelLibraryBulkActions } from '@/hooks/novel_db/useNovelLibraryBulkActions';
import type { BookSummary } from '@/features/novel_db/types';
import { createQueryWrapper } from '@/test/queryTestUtils';

const fetchNovelAuthors = vi.fn();
const fetchSeries = vi.fn();
const patchNovelBookMeta = vi.fn();

vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));
vi.mock('@/features/novel_db/api', () => ({
    fetchNovelAuthors: () => fetchNovelAuthors(),
    fetchSeries: () => fetchSeries(),
    patchNovelBookMeta: (...args: unknown[]) => patchNovelBookMeta(...args),
}));

function makeBook(overrides: Partial<BookSummary>): BookSummary {
    return {
        name: '書籍A',
        authors: [],
        series_id: null,
        series_title: null,
        is_indexed: false,
        page_count: null,
        indexed_at: null,
        thumbnail_url: null,
        ocr_done_at: null,
        volume: null,
        publisher: null,
        asin: null,
        series_index: null,
        read_state: 'unread',
        ...overrides,
    };
}

const books = [
    makeBook({ name: '書籍A', series_id: 'series-a', volume: 3 }),
    makeBook({ name: '書籍B', series_id: 'series-a', volume: 5 }),
    makeBook({ name: '書籍C', series_id: null, volume: null }),
];

describe('useNovelLibraryBulkActions', () => {
    const onMetaRefetch = vi.fn();
    const onClearSelection = vi.fn();

    beforeEach(() => {
        fetchNovelAuthors.mockReset();
        fetchSeries.mockReset();
        patchNovelBookMeta.mockReset();
        onMetaRefetch.mockReset();
        onClearSelection.mockReset();
        vi.mocked(toast.error).mockReset();
        patchNovelBookMeta.mockResolvedValue(undefined);
    });

    function renderBulkActions(selectedNames = new Set(['書籍A', '書籍B'])) {
        return renderHook(
            () =>
                useNovelLibraryBulkActions({
                    books,
                    selectedNames,
                    onMetaRefetch,
                    onClearSelection,
                }),
            { wrapper: createQueryWrapper() },
        );
    }

    it('候補取得に失敗しても空候補の作者ダイアログを開き、通知する', async () => {
        fetchNovelAuthors.mockRejectedValue(new Error('network error'));
        const { result } = renderBulkActions();

        await act(async () => {
            await result.current.openAuthorDialog();
        });

        expect(result.current.showAuthorDialog).toBe(true);
        expect(result.current.allAuthors).toEqual([]);
        expect(toast.error).toHaveBeenCalledWith('作者一覧の取得に失敗しました');
    });

    it('シリーズ候補の取得失敗時も空候補のダイアログを開き、通知する', async () => {
        fetchSeries.mockRejectedValue(new Error('network error'));
        const { result } = renderBulkActions();

        await act(async () => {
            await result.current.openSeriesDialog();
        });

        expect(result.current.showSeriesDialog).toBe(true);
        expect(result.current.allSeriesForDialog).toEqual([]);
        expect(toast.error).toHaveBeenCalledWith('シリーズ一覧の取得に失敗しました');
    });

    it('シリーズ候補の既存最大巻を計算し、選択された書籍を表示順で逐次更新する', async () => {
        fetchSeries.mockResolvedValue([{ id: 'series-a', name: '既存シリーズ', book_count: 2 }]);
        const { result } = renderBulkActions();

        await act(async () => {
            await result.current.openSeriesDialog();
        });
        expect(result.current.allSeriesForDialog).toEqual([
            { id: 'series-a', title: '既存シリーズ', maxIndex: 5 },
        ]);

        await act(async () => {
            await result.current.assignSeries({
                mode: 'existing',
                seriesId: 'series-a',
                indexes: [6, 7],
            });
        });

        expect(patchNovelBookMeta.mock.calls).toEqual([
            ['書籍A.pdf', { series_id: 'series-a', volume: 6 }],
            ['書籍B.pdf', { series_id: 'series-a', volume: 7 }],
        ]);
        expect(onMetaRefetch).toHaveBeenCalledOnce();
        expect(onClearSelection).toHaveBeenCalledOnce();
    });
});
