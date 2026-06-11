import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

vi.mock('../features/novel_db/api', () => ({
    fetchChatSessions: vi.fn(),
    deleteChatSession: vi.fn(),
    fetchChatSessionDetail: vi.fn(),
}));

import { fetchChatSessions, deleteChatSession } from '@/features/novel_db/api';
import { useChatSessions } from '@/hooks/novel_db/useChatSessions';

const mockedFetchSessions = fetchChatSessions as ReturnType<typeof vi.fn>;
const mockedDelete = deleteChatSession as ReturnType<typeof vi.fn>;

function createWrapper() {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
    });
    return ({ children }: { children: React.ReactNode }) =>
        React.createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('useChatSessions', () => {
    beforeEach(() => {
        mockedFetchSessions.mockReset();
        mockedDelete.mockReset();
    });

    it('初回マウントで fetchChatSessions が呼ばれ sessions に反映される', async () => {
        const sessions = [{ id: 1, title: 'セッション1' }];
        mockedFetchSessions.mockResolvedValue(sessions);

        const { result } = renderHook(() => useChatSessions(), { wrapper: createWrapper() });

        await waitFor(() => expect(result.current.isLoading).toBe(false));
        expect(mockedFetchSessions).toHaveBeenCalled();
        expect(result.current.sessions).toEqual(sessions);
    });

    it('fetch 失敗で error がセットされる', async () => {
        mockedFetchSessions.mockRejectedValue(new Error('API error'));

        const { result } = renderHook(() => useChatSessions(), { wrapper: createWrapper() });

        await waitFor(() => expect(result.current.isLoading).toBe(false));
        expect(result.current.error).toBeTruthy();
        expect(result.current.sessions).toEqual([]);
    });

    it('remove(id) で deleteChatSession が呼ばれ sessions が更新される', async () => {
        mockedFetchSessions.mockResolvedValueOnce([{ id: 1 }, { id: 2 }]);
        mockedDelete.mockResolvedValue(undefined);
        mockedFetchSessions.mockResolvedValueOnce([{ id: 2 }]);

        const { result } = renderHook(() => useChatSessions(), { wrapper: createWrapper() });
        await waitFor(() => expect(result.current.sessions).toHaveLength(2));

        await act(async () => {
            await result.current.remove(1);
        });

        expect(mockedDelete).toHaveBeenCalledWith(1);
        await waitFor(() => expect(result.current.sessions).toHaveLength(1));
    });

    it('refetch() で再フェッチできる', async () => {
        mockedFetchSessions.mockResolvedValueOnce([]);
        const { result } = renderHook(() => useChatSessions(), { wrapper: createWrapper() });
        await waitFor(() => expect(result.current.isLoading).toBe(false));

        mockedFetchSessions.mockResolvedValueOnce([{ id: 1 }]);
        await act(async () => {
            await result.current.refetch();
        });

        await waitFor(() => expect(result.current.sessions).toHaveLength(1));
    });

    it('API が配列以外を返した場合は空配列にフォールバック', async () => {
        mockedFetchSessions.mockResolvedValue(null);
        const { result } = renderHook(() => useChatSessions(), { wrapper: createWrapper() });

        await waitFor(() => expect(result.current.isLoading).toBe(false));
        expect(result.current.sessions).toEqual([]);
    });
});
