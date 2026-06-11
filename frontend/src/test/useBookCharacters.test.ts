import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

vi.mock('../features/novel_db/api', () => ({
    fetchBookCharacters: vi.fn(),
}));

import { fetchBookCharacters } from '@/features/novel_db/api';
import { useBookCharacters } from '@/hooks/novel_db/useBookCharacters';

const mockedFetch = fetchBookCharacters as ReturnType<typeof vi.fn>;

function createWrapper() {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
    });
    return ({ children }: { children: React.ReactNode }) =>
        React.createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('useBookCharacters', () => {
    beforeEach(() => mockedFetch.mockReset());

    it('enabled=false ではマウント時に fetch しない', () => {
        renderHook(() => useBookCharacters('book.pdf', false), { wrapper: createWrapper() });
        expect(mockedFetch).not.toHaveBeenCalled();
    });

    it('enabled=true でマウント時に fetch が呼ばれる', async () => {
        mockedFetch.mockResolvedValue([{ name: 'キャラA' }]);
        const { result } = renderHook(() => useBookCharacters('book.pdf', true), {
            wrapper: createWrapper(),
        });

        await waitFor(() => expect(result.current.isLoading).toBe(false));
        expect(mockedFetch).toHaveBeenCalledWith('book.pdf');
        expect(result.current.characters).toHaveLength(1);
    });

    it('fetch 成功でデータが反映される', async () => {
        const chars = [{ name: 'キャラA' }, { name: 'キャラB' }];
        mockedFetch.mockResolvedValue(chars);
        const { result } = renderHook(() => useBookCharacters('book.pdf', true), {
            wrapper: createWrapper(),
        });

        await waitFor(() => expect(result.current.characters).toHaveLength(2));
        expect(result.current.error).toBeNull();
    });

    it('fetch 失敗で error がセットされ characters は空', async () => {
        mockedFetch.mockResolvedValueOnce([]);
        const { result } = renderHook(() => useBookCharacters('book.pdf', true), {
            wrapper: createWrapper(),
        });
        await waitFor(() => expect(result.current.isLoading).toBe(false));

        mockedFetch.mockRejectedValueOnce(new Error('API error'));
        await act(async () => {
            await result.current.refetch();
        });

        expect(result.current.error).toBeTruthy();
        expect(result.current.characters).toEqual([]);
    });

    it('refetch() で再フェッチできる', async () => {
        mockedFetch.mockResolvedValueOnce([]);
        mockedFetch.mockResolvedValueOnce([{ name: 'キャラA' }]);
        const { result } = renderHook(() => useBookCharacters('book.pdf', true), {
            wrapper: createWrapper(),
        });

        await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(1));
        await act(async () => {
            await result.current.refetch();
        });
        expect(result.current.characters).toHaveLength(1);
    });

    it('配列以外のレスポンスは空配列にフォールバック', async () => {
        mockedFetch.mockResolvedValue(null);
        const { result } = renderHook(() => useBookCharacters('book.pdf', true), {
            wrapper: createWrapper(),
        });

        await waitFor(() => expect(result.current.isLoading).toBe(false));
        expect(result.current.characters).toEqual([]);
    });
});
