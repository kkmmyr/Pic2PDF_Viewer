import React from 'react';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../config/api_client', () => ({
    default: { get: vi.fn(), post: vi.fn() },
}));

import apiClient from '@/config/api_client';
import { useBookMetaCore } from '@/hooks/library/useBookMetaCore';
import { useBookView } from '@/hooks/reader/useBookView';
import type { BookMetaMap } from '@/types';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;

const createWrapper = () => {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    return ({ children }: { children: React.ReactNode }) =>
        React.createElement(QueryClientProvider, { client: queryClient }, children);
};

function useCombined(source: string) {
    const core = useBookMetaCore(source);
    const view = useBookView(source);
    return { ...core, ...view };
}

const renderCombined = (initialMeta: BookMetaMap = {}) => {
    mockedGet.mockResolvedValue(initialMeta);
    return renderHook(() => useCombined('doujin'), { wrapper: createWrapper() });
};

describe('useBookView', () => {
    beforeEach(() => {
        mockedGet.mockReset();
        mockedPost.mockReset();
    });

    it('recordView 成功で view_count / last_viewed_at がローカル meta に反映', async () => {
        mockedPost.mockResolvedValue({ view_count: 3, last_viewed_at: 1700000000 });
        const { result } = renderCombined();
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        await act(async () => {
            await result.current.recordView('', 'a.pdf');
        });

        expect(mockedPost).toHaveBeenCalledWith('/api/meta/view', {
            path: '',
            name: 'a.pdf',
            source: 'doujin',
        });
        expect(result.current.meta['a.pdf']?.view_count).toBe(3);
        expect(result.current.meta['a.pdf']?.last_viewed_at).toBe(1700000000);
    });

    it('既存エントリの authors は保持される', async () => {
        mockedPost.mockResolvedValue({ view_count: 1, last_viewed_at: 100 });
        const { result } = renderCombined({
            'a.pdf': { authors: ['作者A'] },
        });
        await waitFor(() => expect(result.current.meta['a.pdf']).toBeDefined());

        await act(async () => {
            await result.current.recordView('', 'a.pdf');
        });

        expect(result.current.meta['a.pdf']?.authors).toEqual(['作者A']);
        expect(result.current.meta['a.pdf']?.view_count).toBe(1);
    });

    it('recordView は失敗を握りつぶし throw しない', async () => {
        mockedPost.mockRejectedValue(new Error('network down'));
        const { result } = renderCombined();
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        await act(async () => {
            // throw しないこと
            await result.current.recordView('', 'a.pdf');
        });
        // ローカル meta は変化しない
        expect(result.current.meta['a.pdf']).toBeUndefined();
    });

    it('path 指定で正しい key にエントリされる', async () => {
        mockedPost.mockResolvedValue({ view_count: 2, last_viewed_at: 200 });
        const { result } = renderCombined();
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        await act(async () => {
            await result.current.recordView('sub', 'a.pdf');
        });

        expect(result.current.meta['sub/a.pdf']?.view_count).toBe(2);
        expect(result.current.meta['a.pdf']).toBeUndefined();
    });

    it('既存 view_count がある状態で recordView 後に値が上書きされる', async () => {
        mockedPost.mockResolvedValue({ view_count: 10, last_viewed_at: 999 });
        const { result } = renderCombined({
            'a.pdf': { authors: [], view_count: 5, last_viewed_at: 100 },
        });
        await waitFor(() => expect(result.current.meta['a.pdf']?.view_count).toBe(5));

        await act(async () => {
            await result.current.recordView('', 'a.pdf');
        });
        expect(result.current.meta['a.pdf']?.view_count).toBe(10);
        expect(result.current.meta['a.pdf']?.last_viewed_at).toBe(999);
    });

    it('recordView レスポンスの read_state がローカル meta に反映される (unread → reading)', async () => {
        mockedPost.mockResolvedValue({
            view_count: 1,
            last_viewed_at: 1,
            incremented: true,
            read_state: 'reading',
        });
        const { result } = renderCombined();
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        await act(async () => {
            await result.current.recordView('', 'a.pdf');
        });
        expect(result.current.meta['a.pdf']?.read_state).toBe('reading');
    });

    it('recordView レスポンスに read_state が無いとローカルの read_state は保持される', async () => {
        // 連打抑制でカウント据え置き時はバックエンドが read_state を返さないケースを想定
        mockedPost.mockResolvedValue({
            view_count: 5,
            last_viewed_at: 200,
            incremented: false,
        });
        const { result } = renderCombined({
            'a.pdf': { authors: ['X'], view_count: 5, read_state: 'done' },
        });
        await waitFor(() => expect(result.current.meta['a.pdf']?.read_state).toBe('done'));

        await act(async () => {
            await result.current.recordView('', 'a.pdf');
        });
        expect(result.current.meta['a.pdf']?.read_state).toBe('done');
    });
});
