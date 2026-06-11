import React from 'react';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../config/api_client', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
        patch: vi.fn(),
        delete: vi.fn(),
    },
}));

import apiClient from '@/config/api_client';
import { useGenres } from '@/hooks/library/useGenres';

const createWrapper = () => {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    return ({ children }: { children: React.ReactNode }) =>
        React.createElement(QueryClientProvider, { client: queryClient }, children);
};

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;
const mockedPatch = apiClient.patch as ReturnType<typeof vi.fn>;
const mockedDelete = apiClient.delete as ReturnType<typeof vi.fn>;

describe('useGenres', () => {
    beforeEach(() => {
        mockedGet.mockReset();
        mockedPost.mockReset();
        mockedPatch.mockReset();
        mockedDelete.mockReset();
    });

    it('マウント時に GET /api/genres?source= を実行して genres を初期化する', async () => {
        mockedGet.mockResolvedValue(['アクション', 'ロマンス']);
        const { result } = renderHook(() => useGenres('doujin'), { wrapper: createWrapper() });

        await waitFor(() => expect(mockedGet).toHaveBeenCalled());
        expect(mockedGet).toHaveBeenCalledWith('/api/genres', { params: { source: 'doujin' } });
        await waitFor(() => expect(result.current.genres).toEqual(['アクション', 'ロマンス']));
    });

    it('GET 失敗時は空配列にフォールバック', async () => {
        mockedGet.mockRejectedValue(new Error('boom'));
        const { result } = renderHook(() => useGenres('doujin'), { wrapper: createWrapper() });

        await waitFor(() => expect(mockedGet).toHaveBeenCalled());
        expect(result.current.genres).toEqual([]);
    });

    it('GET の戻り値が undefined でも空配列に正規化', async () => {
        mockedGet.mockResolvedValue(undefined);
        const { result } = renderHook(() => useGenres('doujin'), { wrapper: createWrapper() });

        await waitFor(() => expect(mockedGet).toHaveBeenCalled());
        expect(result.current.genres).toEqual([]);
    });

    it('addGenre で POST し、レスポンスの genres で list を上書きする', async () => {
        mockedGet.mockResolvedValue(['A']);
        mockedPost.mockResolvedValue({ genres: ['A', 'B'] });

        const { result } = renderHook(() => useGenres('doujin'), { wrapper: createWrapper() });
        await waitFor(() => expect(result.current.genres).toEqual(['A']));

        await act(async () => {
            await result.current.addGenre('B');
        });

        expect(mockedPost).toHaveBeenCalledWith('/api/genres', { source: 'doujin', name: 'B' });
        expect(result.current.genres).toEqual(['A', 'B']);
    });

    it('removeGenre で DELETE し、レスポンスの genres で list を上書きする', async () => {
        mockedGet.mockResolvedValue(['A', 'B']);
        mockedDelete.mockResolvedValue({ genres: ['A'] });

        const { result } = renderHook(() => useGenres('doujin'), { wrapper: createWrapper() });
        await waitFor(() => expect(result.current.genres).toEqual(['A', 'B']));

        await act(async () => {
            await result.current.removeGenre('B');
        });

        expect(mockedDelete).toHaveBeenCalledWith('/api/genres/B', {
            params: { source: 'doujin' },
        });
        expect(result.current.genres).toEqual(['A']);
    });

    it('removeGenre は name を URL エンコードする', async () => {
        mockedGet.mockResolvedValue([]);
        mockedDelete.mockResolvedValue({ genres: [] });

        const { result } = renderHook(() => useGenres('doujin'), { wrapper: createWrapper() });
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        await act(async () => {
            await result.current.removeGenre('プリンセス & コネクト');
        });

        const [calledUrl] = mockedDelete.mock.calls[0];
        expect(calledUrl).toBe(`/api/genres/${encodeURIComponent('プリンセス & コネクト')}`);
    });

    it('reorderGenres は楽観的更新 → PATCH 成功で list が新順序', async () => {
        mockedGet.mockResolvedValue(['A', 'B', 'C']);
        mockedPatch.mockResolvedValue(undefined);

        const { result } = renderHook(() => useGenres('doujin'), { wrapper: createWrapper() });
        await waitFor(() => expect(result.current.genres).toEqual(['A', 'B', 'C']));

        await act(async () => {
            await result.current.reorderGenres(['C', 'A', 'B']);
        });

        expect(mockedPatch).toHaveBeenCalledWith('/api/genres/reorder', {
            source: 'doujin',
            genres: ['C', 'A', 'B'],
        });
        expect(result.current.genres).toEqual(['C', 'A', 'B']);
    });

    it('reorderGenres は PATCH 失敗時に元の順序にロールバックする', async () => {
        mockedGet.mockResolvedValue(['A', 'B', 'C']);
        mockedPatch.mockRejectedValue(new Error('network'));

        const { result } = renderHook(() => useGenres('doujin'), { wrapper: createWrapper() });
        await waitFor(() => expect(result.current.genres).toEqual(['A', 'B', 'C']));

        await act(async () => {
            await result.current.reorderGenres(['C', 'A', 'B']);
        });

        // ロールバック後に元の順序
        expect(result.current.genres).toEqual(['A', 'B', 'C']);
    });

    it('source 変化で再フェッチされる', async () => {
        mockedGet.mockResolvedValueOnce(['gen']).mockResolvedValueOnce(['kin']);
        const { result, rerender } = renderHook(
            ({ src }: { src: 'doujin' | 'comic' }) => useGenres(src),
            { initialProps: { src: 'doujin' }, wrapper: createWrapper() },
        );

        await waitFor(() => expect(result.current.genres).toEqual(['gen']));

        rerender({ src: 'comic' });
        await waitFor(() => expect(result.current.genres).toEqual(['kin']));
        expect(mockedGet).toHaveBeenCalledTimes(2);
    });
});
