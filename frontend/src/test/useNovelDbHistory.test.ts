/**
 * useNovelDbHistory: 一覧取得 + 削除 + refetch。
 */
import { renderHook, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

import { useNovelDbHistory } from '@/hooks/novel_db/useNovelDbHistory';
import type { QaHistoryListResponse } from '@/features/novel_db/types';

vi.mock('../features/novel_db/api', () => ({
    fetchQaHistory: vi.fn(),
    deleteQaHistory: vi.fn(),
}));

import { deleteQaHistory, fetchQaHistory } from '@/features/novel_db/api';

function createWrapper() {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
    });
    return ({ children }: { children: React.ReactNode }) =>
        React.createElement(QueryClientProvider, { client: queryClient }, children);
}

function makeList(ids: number[], total: number): QaHistoryListResponse {
    return {
        items: ids.map((id) => ({
            id,
            asked_at: '2026-05-09 12:00:00',
            finished_at: null,
            scope: { type: 'all', id: null },
            question: `Q${id}`,
            answer_preview: `A${id}`,
            done_reason: 'stop',
        })),
        total,
    };
}

describe('useNovelDbHistory', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('マウント時に一覧を取得', async () => {
        vi.mocked(fetchQaHistory).mockResolvedValue(makeList([1, 2, 3], 3));
        const { result } = renderHook(() => useNovelDbHistory(), { wrapper: createWrapper() });

        await waitFor(() => {
            expect(result.current.items).toHaveLength(3);
            expect(result.current.total).toBe(3);
            expect(result.current.isLoading).toBe(false);
        });
    });

    it('deleteItem で API を呼びリストから除く', async () => {
        vi.mocked(fetchQaHistory).mockResolvedValue(makeList([1, 2], 2));
        vi.mocked(deleteQaHistory).mockResolvedValue();

        const { result } = renderHook(() => useNovelDbHistory(), { wrapper: createWrapper() });
        await waitFor(() => expect(result.current.items).toHaveLength(2));

        await act(async () => {
            await result.current.deleteItem(1);
        });

        expect(deleteQaHistory).toHaveBeenCalledWith(1);
        expect(result.current.items.map((i) => i.id)).toEqual([2]);
        expect(result.current.total).toBe(1);
    });

    it('refetch で再取得', async () => {
        vi.mocked(fetchQaHistory)
            .mockResolvedValueOnce(makeList([1], 1))
            .mockResolvedValueOnce(makeList([1, 2], 2));

        const { result } = renderHook(() => useNovelDbHistory(), { wrapper: createWrapper() });
        await waitFor(() => expect(result.current.items).toHaveLength(1));

        await act(async () => {
            await result.current.refetch();
        });

        await waitFor(() => expect(result.current.items).toHaveLength(2));
    });

    it('取得エラーは error に格納される', async () => {
        vi.mocked(fetchQaHistory).mockRejectedValue(new Error('boom'));
        const { result } = renderHook(() => useNovelDbHistory(), { wrapper: createWrapper() });

        await waitFor(() => {
            expect(result.current.error).toBe('boom');
            expect(result.current.isLoading).toBe(false);
        });
    });
});
