import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../features/novel_db/api', () => ({
    fetchBooks: vi.fn(),
    fetchSeries: vi.fn(),
}));

import { fetchBooks, fetchSeries } from '../features/novel_db/api';
import type { BookSummary, SeriesSummary } from '../features/novel_db/types';
import { useNovelBooksStore } from '../stores/novelBooksStore';
import { useNovelDbBooks } from '../hooks/novel_db/useNovelDbBooks';

const mockedFetchBooks = fetchBooks as ReturnType<typeof vi.fn>;
const mockedFetchSeries = fetchSeries as ReturnType<typeof vi.fn>;

const resetStore = () =>
    useNovelBooksStore.setState({ books: [], series: [], isLoading: false, error: null });

describe('useNovelDbBooks', () => {
    beforeEach(() => {
        mockedFetchBooks.mockReset();
        mockedFetchSeries.mockReset();
        resetStore();
    });

    it('books=0 かつ isLoading=false のときマウントで fetch が呼ばれる', async () => {
        mockedFetchBooks.mockResolvedValue([{ name: '本A' }]);
        mockedFetchSeries.mockResolvedValue([]);

        renderHook(() => useNovelDbBooks());

        await waitFor(() => expect(mockedFetchBooks).toHaveBeenCalledTimes(1));
    });

    it('isLoading=true のときマウントしても fetch を追加しない', async () => {
        useNovelBooksStore.setState({ isLoading: true });
        mockedFetchBooks.mockResolvedValue([]);
        mockedFetchSeries.mockResolvedValue([]);

        renderHook(() => useNovelDbBooks());

        await act(async () => {
            await Promise.resolve();
        });
        expect(mockedFetchBooks).not.toHaveBeenCalled();
    });

    it('store の books/series/isLoading/error が返る', async () => {
        const books = [{ name: '本A' }] as BookSummary[];
        const series = [{ id: 's1' }] as SeriesSummary[];
        useNovelBooksStore.setState({ books, series, isLoading: false, error: null });

        const { result } = renderHook(() => useNovelDbBooks());

        expect(result.current.books).toEqual(books);
        expect(result.current.series).toEqual(series);
        expect(result.current.isLoading).toBe(false);
        expect(result.current.error).toBeNull();
    });

    it('refetch で再フェッチできる', async () => {
        mockedFetchBooks.mockResolvedValue([]);
        mockedFetchSeries.mockResolvedValue([]);

        const { result } = renderHook(() => useNovelDbBooks());
        await waitFor(() => expect(mockedFetchBooks).toHaveBeenCalledTimes(1));

        mockedFetchBooks.mockResolvedValue([{ name: '本B' }]);
        await act(async () => {
            await result.current.refetch();
        });
        expect(mockedFetchBooks).toHaveBeenCalledTimes(2);
    });
});
