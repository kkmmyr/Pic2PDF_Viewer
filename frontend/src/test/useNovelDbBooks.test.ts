import React from 'react';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../features/novel_db/api', () => ({
    fetchBooks: vi.fn(),
    fetchSeries: vi.fn(),
}));

import { fetchBooks, fetchSeries } from '@/features/novel_db/api';
import { useNovelDbBooks } from '@/hooks/novel_db/useNovelDbBooks';

const mockedFetchBooks = fetchBooks as ReturnType<typeof vi.fn>;
const mockedFetchSeries = fetchSeries as ReturnType<typeof vi.fn>;

const createWrapper = () => {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
    });
    return ({ children }: { children: React.ReactNode }) =>
        React.createElement(QueryClientProvider, { client: queryClient }, children);
};

describe('useNovelDbBooks', () => {
    beforeEach(() => {
        mockedFetchBooks.mockReset();
        mockedFetchSeries.mockReset();
    });

    it('マウント時に fetchBooks / fetchSeries が呼ばれる', async () => {
        mockedFetchBooks.mockResolvedValue([{ name: '本A' }]);
        mockedFetchSeries.mockResolvedValue([]);

        renderHook(() => useNovelDbBooks(), { wrapper: createWrapper() });

        await waitFor(() => expect(mockedFetchBooks).toHaveBeenCalledTimes(1));
        expect(mockedFetchSeries).toHaveBeenCalledTimes(1);
    });

    it('books / series が返る', async () => {
        const books = [{ name: '本A' }];
        const series = [{ id: 's1', title: 'シリーズ1' }];
        mockedFetchBooks.mockResolvedValue(books);
        mockedFetchSeries.mockResolvedValue(series);

        const { result } = renderHook(() => useNovelDbBooks(), { wrapper: createWrapper() });

        await waitFor(() => expect(result.current.books).toEqual(books));
        expect(result.current.series).toEqual(series);
        expect(result.current.isLoading).toBe(false);
        expect(result.current.error).toBeNull();
    });

    it('API が配列以外を返した場合は空配列にフォールバック', async () => {
        mockedFetchBooks.mockResolvedValue(null);
        mockedFetchSeries.mockResolvedValue(undefined);

        const { result } = renderHook(() => useNovelDbBooks(), { wrapper: createWrapper() });

        await waitFor(() => expect(result.current.isLoading).toBe(false));
        expect(result.current.books).toEqual([]);
        expect(result.current.series).toEqual([]);
    });

    it('refetch で再フェッチできる', async () => {
        mockedFetchBooks.mockResolvedValue([]);
        mockedFetchSeries.mockResolvedValue([]);

        const { result } = renderHook(() => useNovelDbBooks(), { wrapper: createWrapper() });
        await waitFor(() => expect(mockedFetchBooks).toHaveBeenCalledTimes(1));

        mockedFetchBooks.mockResolvedValue([{ name: '本B' }]);
        await act(async () => {
            await result.current.refetch();
        });
        await waitFor(() => expect(result.current.books).toEqual([{ name: '本B' }]));
        expect(mockedFetchBooks).toHaveBeenCalledTimes(2);
    });
});
