import { act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../features/novel_db/api', () => ({
    fetchBooks: vi.fn(),
    fetchSeries: vi.fn(),
}));

import { fetchBooks, fetchSeries } from '../features/novel_db/api';
import { useNovelBooksStore } from '../stores/novelBooksStore';

const mockedFetchBooks = fetchBooks as ReturnType<typeof vi.fn>;
const mockedFetchSeries = fetchSeries as ReturnType<typeof vi.fn>;

const resetStore = () => useNovelBooksStore.setState({ books: [], series: [], isLoading: false, error: null });

describe('novelBooksStore', () => {
    beforeEach(() => {
        mockedFetchBooks.mockReset();
        mockedFetchSeries.mockReset();
        resetStore();
    });

    it('初期状態は books/series 空・isLoading false・error null', () => {
        const state = useNovelBooksStore.getState();
        expect(state.books).toEqual([]);
        expect(state.series).toEqual([]);
        expect(state.isLoading).toBe(false);
        expect(state.error).toBeNull();
    });

    it('fetch() で fetchBooks / fetchSeries が呼ばれ store に反映される', async () => {
        const books = [{ name: '本A' }];
        const series = [{ id: 's1', title: 'シリーズ1' }];
        mockedFetchBooks.mockResolvedValue(books);
        mockedFetchSeries.mockResolvedValue(series);

        await act(async () => {
            await useNovelBooksStore.getState().fetch();
        });

        const state = useNovelBooksStore.getState();
        expect(state.books).toEqual(books);
        expect(state.series).toEqual(series);
        expect(state.isLoading).toBe(false);
        expect(state.error).toBeNull();
    });

    it('fetch 中は isLoading=true になる', async () => {
        let resolveBooks: (v: unknown) => void = () => {};
        mockedFetchBooks.mockReturnValue(new Promise((r) => { resolveBooks = r; }));
        mockedFetchSeries.mockResolvedValue([]);

        const fetchPromise = act(async () => {
            void useNovelBooksStore.getState().fetch();
        });

        expect(useNovelBooksStore.getState().isLoading).toBe(true);
        resolveBooks([]);
        await fetchPromise;
    });

    it('並列 fetch() 呼び出しで 2 重フェッチが起きない', async () => {
        mockedFetchBooks.mockResolvedValue([]);
        mockedFetchSeries.mockResolvedValue([]);

        await act(async () => {
            await Promise.all([
                useNovelBooksStore.getState().fetch(),
                useNovelBooksStore.getState().fetch(),
            ]);
        });

        expect(mockedFetchBooks).toHaveBeenCalledTimes(1);
    });

    it('fetch 失敗時に error がセットされ books/series は空のまま', async () => {
        mockedFetchBooks.mockRejectedValue(new Error('API エラー'));
        mockedFetchSeries.mockRejectedValue(new Error('API エラー'));

        await act(async () => {
            await useNovelBooksStore.getState().fetch();
        });

        const state = useNovelBooksStore.getState();
        expect(state.error).toBeTruthy();
        expect(state.books).toEqual([]);
        expect(state.isLoading).toBe(false);
    });

    it('成功後に再度 fetch() で books が更新される', async () => {
        mockedFetchBooks.mockResolvedValueOnce([{ name: '本A' }]);
        mockedFetchSeries.mockResolvedValue([]);

        await act(async () => {
            await useNovelBooksStore.getState().fetch();
        });
        expect(useNovelBooksStore.getState().books).toHaveLength(1);

        mockedFetchBooks.mockResolvedValueOnce([{ name: '本A' }, { name: '本B' }]);
        await act(async () => {
            await useNovelBooksStore.getState().fetch();
        });
        expect(useNovelBooksStore.getState().books).toHaveLength(2);
    });

    it('API が配列以外を返した場合は空配列にフォールバック', async () => {
        mockedFetchBooks.mockResolvedValue(null);
        mockedFetchSeries.mockResolvedValue(undefined);

        await act(async () => {
            await useNovelBooksStore.getState().fetch();
        });

        expect(useNovelBooksStore.getState().books).toEqual([]);
        expect(useNovelBooksStore.getState().series).toEqual([]);
    });
});
